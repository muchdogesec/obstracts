import io
import logging
import time
from urllib.parse import urljoin
from celery import shared_task, chain, current_task, Task as CeleryTask
from django.conf import settings
import typing

from dogesec_commons.stixifier.stixifier import StixifyProcessor, ReportProperties
from dogesec_commons.stixifier.summarizer import parse_summarizer_model
from ..server.models import Job, FeedProfile
from ..server import models
from django.core.cache import cache
from history4feed.app import models as h4f_models

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

class ShouldRetry(Exception):
    pass

class CancelledJob(Exception):
    pass


@shared_task
def job_completed_with_error(job_id):
    job = Job.objects.get(pk=job_id)
    if job.state == models.JobState.CANCELLED:
        pass
    elif job.processed_items == 0 and job.failed_processes > 0:
        job.update_state(models.JobState.PROCESS_FAILED)
    else:
        job.update_state(models.JobState.PROCESSED)

    logging.info("removing queue lock for feed `%s`", str(job.feed.id))
    if cache.delete(get_lock_id(job)):
        logging.info("lock deleted")
    else:
        logging.error("Failed to remove lock")

    job.save()


def new_task(h4f_job: h4f_models.Job, profile_id):
    return create_job_entry(h4f_job, profile_id)

def create_job_entry(h4f_job: h4f_models.Job, profile_id):
    job = Job.objects.create(history4feed_job=h4f_job, feed_id=h4f_job.feed_id, profile_id=profile_id)
    return job


@shared_task
def start_processing(job_id):
    job = Job.objects.get(pk=job_id)
    logging.info(
        f"processing {job_id=}, {job.feed_id=}, {current_task.request.root_id=}"
    )
    posts = [f.post.id for f in h4f_models.FulltextJob.objects.filter(job=job.history4feed_job).all()]
    
    logging.info("processing %d posts for job %s", len(posts), job_id)
    tasks = [wait_in_queue.si(job_id)] + [process_post.si(job_id, str(post_id)) for post_id in posts]
    tasks.append(job_completed_with_error.si(job_id))
    return chain(tasks).apply_async()


@shared_task(bind=True, default_retry_delay=10)
def wait_in_queue(self: CeleryTask, job_id):
    logging.info("job with id %s completed processing", job_id)
    job = Job.objects.get(pk=job_id)
    if job.is_cancelled():
        job.errors.append("job cancelled while in queue")
        job.save()
        return False
    if not queue_lock(job):
        return self.retry(max_retries=300)
    job.update_state(models.JobState.PROCESSING)
    job.save()
    return True


@shared_task
def process_post(job_id, post_id, *args):
    job = Job.objects.get(pk=job_id)
    post = h4f_models.Post.objects.get(pk=post_id)
    try:
        if job.is_cancelled():
            raise CancelledJob()
        file, _ = models.File.objects.update_or_create(
            post_id=post_id,
            defaults=dict(
                feed_id=job.feed.id,
                profile_id=job.profile.id,
                profile=job.profile,
                processed=False,
            ),
        )

        stream = io.BytesIO(post.description.encode())
        stream.name = f"post-{post_id}.html"
        processor = StixifyProcessor(
            stream,
            job.profile,
            job_id=f"{post.id}+{job.id}",
            file2txt_mode="html_article",
            report_id=post_id,
            base_url=post.link,
        )
        processor.collection_name = job.feed.collection_name
        properties = ReportProperties(
            name=post.title,
            identity=file.feed.identity,
            tlp_level="clear",
            confidence=0,
            labels=[],
            created=file.post.pubdate,
            kwargs=dict(
                external_references=[
                    dict(source_name="post_link", url=post.link),
                    dict(source_name="obstracts_feed_id", external_id=str(job.feed.id)),
                    dict(
                        source_name="obstracts_profile_id",
                        external_id=str(job.profile.id),
                    ),
                ]
            ),
        )
        processor.setup(
            properties,
            dict(_obstracts_feed_id=str(job.feed.id), _obstracts_post_id=post_id),
        )
        processor.process()

        if processor.incident:
            file.ai_describes_incident = processor.incident.describes_incident
            file.ai_incident_summary = processor.incident.explanation
            file.ai_incident_classification = processor.incident.incident_classification

        file.txt2stix_data = processor.txt2stix_data.model_dump(
            mode="json", exclude_defaults=True, exclude_unset=True, exclude_none=True
        )
        file.summary = processor.summary

        file.markdown_file.save("markdown.md", processor.md_file.open(), save=True)
        models.FileImage.objects.filter(report=file).delete()  # remove old references

        for image in processor.md_images:
            models.FileImage.objects.create(
                report=file, file=File(image, image.name), name=image.name
            )

        file.processed = True
        file.save()
        job.processed_items += 1
    except CancelledJob:
        msg = f"job cancelled by user for post {post_id}"
        logging.error(msg, exc_info=True)
        job.errors.append(msg)
    except Exception as e:
        msg = f"processing failed for post {post_id}"
        logging.error(msg, exc_info=True)
        job.failed_processes += 1
        job.errors.append(msg)
    job.save()
    return job_id


from celery import signals
@signals.worker_ready.connect
def mark_old_jobs_as_failed(**kwargs):
    models.Job.objects.filter(state=models.JobState.RETRIEVING).update(state=models.JobState.RETRIEVE_FAILED)
    models.Job.objects.filter(state__in=[models.JobState.RETRIEVING, models.JobState.QUEUED, models.JobState.PROCESSING]).update(state=models.JobState.CANCELLED)
