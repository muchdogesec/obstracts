import io
import logging
from urllib.parse import urljoin
from celery import shared_task, chain, current_task
from django.conf import settings
import typing

from dogesec_commons.stixifier.stixifier import StixifyProcessor, ReportProperties
from dogesec_commons.stixifier.summarizer import parse_summarizer_model
from ..server.models import Job, FeedProfile
from ..server import models

from django.core.files.base import File

if typing.TYPE_CHECKING:
    from ..import settings

POLL_INTERVAL = 30

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
        job.state = models.JobState.PROCESSING
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
    job.save()


@shared_task(default_retry_delay=POLL_INTERVAL)
def poll_job(job_id):
    logging.info("root_id: %s and job_id: %s", current_task.request.root_id, current_task.request.id)
    try:
        return poll_once(job_id)
    except BaseException as e:
        logging.exception(e)
        current_task.retry(max_retries=200)


def new_task(feed_dict, profile_id, summary_provider):
    kwargs = dict(id=feed_dict["feed_id"], profile_id=profile_id)
    if title := feed_dict.get("title"):
        kwargs.update(title=title)
    feed, _ = FeedProfile.objects.update_or_create(defaults=kwargs, id=feed_dict["feed_id"])
    job = Job.objects.create(id=feed_dict["job_id"], feed=feed, profile_id=profile_id)
    (poll_job.s(job.id) | start_processing.s(job.id, summary_provider)).apply_async(
        countdown=5, root_id=job.id, task_id=job.id
    )
    return job

def new_post_patch_task(input_dict, profile_id, summary_provider):
    job = Job.objects.create(id=input_dict["job_id"], feed_id=input_dict["feed_id"], profile_id=profile_id)
    (poll_job.s(job.id) | start_processing.s(job.id, summary_provider)).apply_async(
        countdown=5, root_id=job.id, task_id=job.id
    )
    return job


@shared_task
def start_processing(h4f_job, job_id, summary_provider):
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
            f"/api/v1/feeds/{job.feed_id}/posts/",
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
    tasks = [process_post.si(job_id, post, summary_provider) for post in posts]
    tasks.append(job_completed_with_error.si(job_id))
    return chain(tasks).apply_async()


@shared_task
def set_job_completed(job_id):
    logging.info("job with id %s completed processing", job_id)
    job = Job.objects.get(id=job_id)
    job.state = models.JobState.PROCESSED
    job.save()


@shared_task
def process_post(job_id, post, summary_provider, *args):
    job = Job.objects.get(id=job_id)
    post_id = str(post['id'])
    try:
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
        processor.process()
        file, _ = models.File.objects.get_or_create(post_id=post_id)
        if summary_provider:
            logging.info(f"summarizing report {processor.report_id} using `{summary_provider}`")
            try:
                summary_provider = parse_summarizer_model(summary_provider)
                file.summary = summary_provider.summarize(processor.output_md)
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