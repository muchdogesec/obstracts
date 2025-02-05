import io
import logging
from urllib.parse import urljoin
from celery import shared_task, chain, current_task, Task as CeleryTask
from django.conf import settings
import typing

from dogesec_commons.stixifier.stixifier import StixifyProcessor, ReportProperties
from dogesec_commons.stixifier.summarizer import parse_summarizer_model
from txt2stix.txt2stix import parse_model
from ..server.models import Job, FeedProfile
from ..server import models
from django.core.cache import cache

from django.core.files.base import File

if typing.TYPE_CHECKING:
    from ..import settings

POLL_INTERVAL = 30
LOCK_EXPIRE = 60 * 10


def get_lock_id(job: Job):
    lock_id = f"feed-lock-{job.feed.id}"
    logging.debug("using lock id %s", lock_id)
    return lock_id

def queue_lock(job: Job):
    logging.debug("lock_value = {v}".format(v=cache.get(get_lock_id(job))))
    lock_value = dict(feed_id=str(job.feed.id))
    if job:
        lock_value["job_id"] = str(job.id)
        
    status = cache.add(get_lock_id(job), lock_value, timeout=LOCK_EXPIRE)
    return status

import requests


class ShouldRetry(Exception):
    pass


def make_h4f_request(path, method="GET", params=None, body=None, headers={}):
    headers = headers or {}
    try:
        url = urljoin(settings.HISTORY4FEED_URL, path)
        headers["host"] = "localhost"
        resp = requests.request(method, url, params=params, headers=headers, data=body)
        return resp
    except Exception as e:
        logging.exception(e)
        raise


def poll_once(job_id):
    logging.info("polling h4f for job with id = %s", job_id)
    job_resp = make_h4f_request(f"/api/v1/jobs/{job_id}/")
    if not job_resp.ok:
        return False
    h4f_job = job_resp.json()
    logging.info(f"[{job_resp.status_code=}] job_id: {job_id}")
    job = Job.objects.get(pk=job_id)
    job.history4feed_status = h4f_job["state"]
    job.history4feed_job = h4f_job
    job.item_count = len(h4f_job["urls"].get('retrieved', []))
    if job.history4feed_status == models.H4FState.SUCCESS:
        job.state = models.JobState.QUEUED
        job.save()
        return h4f_job
    elif job.history4feed_status == models.H4FState.FAILED:
        job.state = models.JobState.RETRIEVE_FAILED
        job.save()
        return False
    job.save()
    raise ShouldRetry()


@shared_task
def job_completed_with_error(job_id):
    job = Job.objects.get(pk=job_id)
    if job.failed_processes > 0:
        job.state = models.JobState.PROCESS_FAILED
    else:
        job.state = models.JobState.PROCESSED

    logging.info("removing queue lock for feed `%s`", str(job.feed.id))
    if cache.delete(get_lock_id(job)):
        logging.info("lock deleted")
    else:
        logging.error("Failed to remove lock")

    job.save()


@shared_task(default_retry_delay=POLL_INTERVAL)
def poll_job(job_id):
    logging.info("root_id: %s and job_id: %s", current_task.request.root_id, current_task.request.id)
    try:
        return poll_once(job_id)
    except BaseException as e:
        logging.exception(e)
        current_task.retry(max_retries=200)


def new_task(feed_dict, profile_id, ai_content_check_variable):
    kwargs = dict(id=feed_dict["feed_id"], profile_id=profile_id)
    if title := feed_dict.get("title"):
        kwargs.update(title=title)
    feed, _ = FeedProfile.objects.update_or_create(defaults=kwargs, id=feed_dict["feed_id"])
    job = Job.objects.create(id=feed_dict["job_id"], feed=feed, profile_id=profile_id, ai_content_check_variable=ai_content_check_variable)
    (poll_job.s(job.id) | start_processing.s(job.id)).apply_async(
        countdown=5, root_id=job.id, task_id=job.id
    )
    return job

def new_post_patch_task(input_dict, profile_id, ai_content_check_variable):
    job = Job.objects.create(id=input_dict["job_id"], feed_id=input_dict["feed_id"], profile_id=profile_id, ai_content_check_variable=ai_content_check_variable)
    (poll_job.s(job.id) | start_processing.s(job.id)).apply_async(
        countdown=5, root_id=job.id, task_id=job.id
    )
    return job


@shared_task
def start_processing(h4f_job, job_id):
    job = Job.objects.get(id=job_id)
    logging.info(
        f"processing {job_id=}, {job.feed_id=}, {current_task.request.root_id=}"
    )
    if not h4f_job:
        if job.state == models.JobState.RETRIEVING:
            job.state = models.JobState.RETRIEVE_FAILED
            job.save()
        return []

    posts = []
    current_page = 1
    item_count = job.item_count
    while len(posts) < item_count:
        resp = make_h4f_request(
            f"/api/v1/posts/",
            params={"job_id": job_id, "page": current_page},
        )
        if resp.ok:
            data = resp.json()
            posts.extend(data["posts"])
            item_count = data["total_results_count"]
            current_page += 1
        else:
            logging.error(
                f"got HTTP {resp.status_code} while processing job for {job_id}. body: {resp.text}, count: {len(posts)}"
            )
            break
    logging.info("processing %d posts for job %s", len(posts), job_id)
    tasks = [wait_in_queue.si(job_id)] + [process_post.si(job_id, post) for post in posts]
    tasks.append(job_completed_with_error.si(job_id))
    return chain(tasks).apply_async()


@shared_task(bind=True, default_retry_delay=10)
def wait_in_queue(self: CeleryTask, job_id):
    logging.info("job with id %s completed processing", job_id)
    job = Job.objects.get(id=job_id)
    if not queue_lock(job):
        return self.retry(max_retries=300)
    job.state = models.JobState.PROCESSING
    job.save()
    return True


@shared_task
def process_post(job_id, post, *args):
    job = Job.objects.get(id=job_id)
    post_id = str(post['id'])
    try:
        file, _ = models.File.objects.update_or_create(post_id=post_id, defaults=dict(feed_id=job.feed.id, profile_id=job.profile.id, profile=job.profile))

        stream = io.BytesIO(post['description'].encode())
        stream.name = f"post-{post_id}.html"
        processor = StixifyProcessor(stream, job.profile, job_id=job.id, file2txt_mode="html_article", report_id=post_id, base_url=post['link'])
        processor.collection_name = job.feed.collection_name
        properties = ReportProperties(
            name=post['title'],
            identity=settings.OBSTRACTS_IDENTITY,
            tlp_level="clear",
            confidence=0,
            labels=[],
            created=job.created,
            kwargs=dict(external_references=[
                dict(source_name='post_link', url=post['link']),
                dict(source_name='obstracts_feed_id', external_id=job.feed.id),
                dict(source_name='obstracts_profile_id', external_id=job.profile.id),
            ])
        )
        processor.setup(properties, dict(_obstracts_feed_id=str(job.feed.id), _obstracts_post_id=post_id))
        ## processor.process() start
        logging.info(f"running file2txt on {processor.task_name}")
        processor.file2txt()
        if job.ai_content_check_variable:
            ai_content_check_model = parse_model(job.ai_content_check_variable)
            content_described  = ai_content_check_model.check_content(processor.output_md)
            file.describes_incident = content_described.describes_incident
            file.incident_summary = content_described.explanation
        if not job.ai_content_check_variable or file.describes_incident:
            logging.info(f"running txt2stix on {processor.task_name}")
            bundler = processor.txt2stix()
            processor.write_bundle(bundler)
            logging.info(f"uploading {processor.task_name} to arangodb via stix2arango")
            processor.upload_to_arango()
        # return bundler.report.id
        ## processor.process() endss

        if job.profile.ai_summary_provider:
            logging.info(f"summarizing report {processor.report_id} using `{job.profile.ai_summary_provider}`")
            try:
                summary_extractor = parse_summarizer_model(job.profile.ai_summary_provider)
                file.summary = summary_extractor.summarize(processor.output_md)
            except BaseException as e:
                print(f"got err {e}")
                logging.info(f"got err {e}", exc_info=True)

        file.markdown_file.save('markdown.md', processor.md_file.open(), save=True)
        models.FileImage.objects.filter(report=file).delete() # remove old references

        for image in processor.md_images:
            models.FileImage.objects.create(report=file, file=File(image, image.name), name=image.name)
        file.save()
        job.processed_items += 1
    except Exception as e:
        logging.error("failed to process post with id: %s", post["id"])
        logging.exception(e)
        job.failed_processes += 1
    job.save()
    return job_id




from celery import signals
@signals.worker_ready.connect
def mark_old_jobs_as_failed(**kwargs):
    models.Job.objects.filter(state=models.JobState.RETRIEVING).update(state=models.JobState.RETRIEVE_FAILED)
    models.Job.objects.filter(state__in=[models.JobState.RETRIEVING, models.JobState.QUEUED, models.JobState.PROCESSING]).update(state=models.JobState.PROCESS_FAILED)