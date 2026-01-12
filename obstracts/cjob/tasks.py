import io
import logging
import uuid
from celery import shared_task, chain, current_task, Task as CeleryTask
from django.db import transaction
import typing
from celery.exceptions import SoftTimeLimitExceeded, TimeLimitExceeded

from dogesec_commons.stixifier.stixifier import StixifyProcessor, ReportProperties
from txt2stix.txt2stix import Txt2StixData
import requests

from obstracts.cjob import helpers
from ..server.models import Job
from ..server import models
from django.core.cache import cache
from history4feed.app import models as h4f_models

from django.core.files.base import File
from django.conf import settings

if typing.TYPE_CHECKING:
    from .. import settings

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
    if job.state in [models.JobState.CANCELLING, models.JobState.CANCELLED]:
        job.update_state(models.JobState.CANCELLED)
    elif job.processed_items == 0 and job.failed_processes > 0:
        job.update_state(models.JobState.PROCESS_FAILED)
    else:
        job.update_state(models.JobState.PROCESSED)

    if job.feed:
        logging.info("removing queue lock for feed `%s`", str(job.feed.id))
        if cache.delete(get_lock_id(job)):
            logging.info("lock deleted")
        else:
            logging.error("Failed to remove lock")

    job.save()


def create_job_entry(h4f_job: h4f_models.Job, profile_id, **extra):
    job = Job.objects.create(
        id=h4f_job.id,
        history4feed_job=h4f_job,
        feed_id=h4f_job.feed_id,
        profile_id=profile_id,
        type=models.JobType.FEED_INDEX,
    )
    if extra and extra.get('pdfshift_cookie_settings'):
        job.feed.pdfshift_cookie_settings = extra['pdfshift_cookie_settings']
        job.feed.save()
    return job


def create_pdf_reindex_job(feed, files):
    job = models.Job.objects.create(
        id=uuid.uuid4(),
        type=models.JobType.PDF_INDEX,
        feed_id=feed.id,
        state=models.JobState.QUEUED,
    )

    pdf_tasks = [reindex_pdf_for_post.si(job.id, f.post_id) for f in files]
    pdf_tasks.append(job_completed_with_error.si(job.id))
    chain(pdf_tasks).apply_async()

    return job

def create_reprocessing_job(feed, posts: list[models.h4f_models.Post], options: dict = None):
    job  = models.Job.objects.create(
        id=uuid.uuid4(),
        type=models.JobType.REPROCESS_POSTS,
        feed_id=feed.id,
        profile_id=options.pop('profile_id', None),
        state=models.JobState.QUEUED,
        extra=options,
    )
    tasks = [wait_in_queue.si(job.id)]
    profile_id = job.profile_id
    for post in posts:
        if options['skip_extraction'] and getattr(post, 'obstracts_post', None):
            profile_id = post.obstracts_post.profile_id
        tasks.append(process_post.si(str(job.id), str(post.id), profile_id=str(profile_id)))
    t = chain(tasks)
    t.stamp(obstracts_id=str(job.id))
    t |= job_completed_with_error.si(job.id)
    t.apply_async()
    return job

@shared_task(bind=True)
def start_processing(self, job_id):
    job = Job.objects.get(pk=job_id)
    logging.info(
        f"processing {job_id=}, {job.feed_id=}, {current_task.request.root_id=}"
    )
    posts = [
        f.post.id
        for f in h4f_models.FulltextJob.objects.filter(
            job=job.history4feed_job, status=h4f_models.FullTextState.RETRIEVED
        ).all()
    ]

    logging.info("processing %d posts for job %s", len(posts), job_id)
    tasks = [wait_in_queue.si(job_id)] + [
        process_post.si(job_id, str(post_id)) for post_id in posts
    ]
    t = chain(tasks)
    t.stamp(obstracts_id=str(job.id))
    t |= job_completed_with_error.si(job_id)
    return self.replace(t)

@shared_task(bind=True, default_retry_delay=10)
def wait_in_queue(self: CeleryTask, job_id):
    logging.info("job with id %s completed processing", job_id)
    job = Job.objects.get(pk=job_id)
    if job.is_cancelled():
        job.errors.append("job cancelled while in queue")
        job.save(update_fields=["errors"])
        return False
    if not queue_lock(job):
        return self.retry(max_retries=300)
    job.update_state(models.JobState.PROCESSING)
    return True


def download_pdf(url, is_demo=False, cookie_consent_mode=None):
    params = {
        "source": url,
        "timeout": 30,
        "delay": 1000,
        "css": "div.cookie-banner, .cookie-consent, #cookie-consent, .cc-window { display: none !important; }",
    }
    if cookie_consent_mode == models.PDFCookieConsentMode.disable_all_js:
        params.update(disable_javascript=True)
    else:
        params.update(
            javascript='document.querySelectorAll(".cookie-banner, .cookie-consent, #cookie-consent").forEach(e => e.remove());'
        )
    if is_demo:
        params.update(sandbox=True)
    response = requests.post(
        f"https://api.pdfshift.io/v3/convert/pdf",
        headers={"X-API-Key": settings.PDFSHIFT_API_KEY},
        json=params,
    )
    if not response.ok:
        print(response.content)
    response.raise_for_status()
    return response.content

@shared_task
def update_vulnerabilities(job_id):
    job = models.Job.objects.get(pk=job_id)
    state = models.JobState.PROCESSED
    try:
        helpers.run_on_collections(job)
    except Exception as e:
        job.errors.append(str(e))
        job.save(update_fields=["errors"])
        state = models.JobState.PROCESS_FAILED
    job.update_state(state)

@shared_task
def add_pdf_to_post(job_id, post_id):
    job = models.Job.objects.get(pk=job_id)
    post_file = models.File.objects.get(pk=post_id)
    feedp = models.FeedProfile.objects.get(feed_id=post_file.feed_id)
    try:
        pdf_bytes = download_pdf(
            post_file.post.link, cookie_consent_mode=feedp.pdfshift_cookie_settings
        )
        post_file.pdf_file.save(
            f"{post_file.post.title}.pdf", io.BytesIO(pdf_bytes), save=False
        )
        post_file.save(update_fields=["pdf_file"])
    except Exception as e:
        logging.exception(f"process file to pdf failed for {post_file.pk}")
        job.errors.append(f"process file to pdf failed for {post_file.pk}")
        job.save()


@shared_task(bind=True, soft_time_limit=settings.PROCESSING_TIMEOUT_SECONDS, time_limit=settings.PROCESSING_TIMEOUT_SECONDS + 20)
def process_post(self, job_id, post_id, profile_id=None, *args):
    from obstracts.server.views import PostOnlyView

    job = Job.objects.get(pk=job_id)
    post = h4f_models.Post.objects.get(pk=post_id)
    profile = job.profile
    if profile_id:
        profile = models.Profile.objects.get(pk=profile_id)
    try:
        if job.is_cancelled():
            raise CancelledJob()
        file, _ = models.File.objects.update_or_create(
            post_id=post_id,
            defaults=dict(
                processed=False,
            ),
            create_defaults=dict(
                feed_id=job.feed.id,
                profile_id=profile.id,
            )
        )

        print("ksajjhsjhs", file.pdf_file)
        if profile.generate_pdf and (job.type != models.JobType.REPROCESS_POSTS or not file.pdf_file):
            add_pdf_to_post.delay(job_id, post_id)
        
        PostOnlyView.remove_report_objects(file)

        mode = "html_article"
        if job.type == models.JobType.REPROCESS_POSTS:
            stream = file.markdown_file.open('rb')
            mode = "md"
            stream.name = f"post-{post_id}.html"
        else:
            stream = io.BytesIO(post.description.encode())
            stream.name = f"post-{post_id}.html"

        processor = StixifyProcessor(
            stream,
            profile,
            job_id=f"{post.id}+{job.id}",
            file2txt_mode=mode,
            report_id=post_id,
            base_url=post.link,
        )
        processor.collection_name = job.feed.collection_name
        properties = ReportProperties(
            name=post.title,
            identity=file.feed.identity,
            tlp_level="clear",
            confidence=0,
            labels=[f"tag.{cat.name}" for cat in post.categories.all()],
            created=file.post.pubdate,
            kwargs=dict(
                external_references=[
                    dict(source_name="post_link", url=post.link),
                    dict(source_name="obstracts_feed_id", external_id=str(job.feed.id)),
                    dict(
                        source_name="obstracts_profile_id",
                        external_id=str(profile.id),
                    ),
                ]
            ),
        )
        processor.setup(
            properties,
            dict(_obstracts_feed_id=str(job.feed.id), _obstracts_post_id=post_id),
        )
        if job.type == models.JobType.REPROCESS_POSTS:
            processor.output_md = file.markdown_file.open().read().decode()
            txt2stix_data = None
            if job.extra['skip_extraction']:
                if not file.txt2stix_data:
                    raise Exception("no existing extraction data to use for reprocess with skip_extraction=true")
                txt2stix_data = Txt2StixData.model_validate(file.txt2stix_data)
            processor.txt2stix(txt2stix_data)
            processor.write_bundle(processor.bundler)
            processor.upload_to_arango()
        else:
            processor.process()

        if processor.incident:
            file.ai_describes_incident = processor.incident.describes_incident
            file.ai_incident_summary = processor.incident.explanation
            file.ai_incident_classification = processor.incident.incident_classification

        file.txt2stix_data = processor.txt2stix_data.model_dump(
            mode="json", exclude_defaults=True, exclude_unset=True, exclude_none=True
        )
        file.summary = processor.summary

        if job.type != models.JobType.REPROCESS_POSTS:
            file.markdown_file.save("markdown.md", processor.md_file.open(), save=False)
            models.FileImage.objects.filter(report=file).delete()  # remove old references

            for image in processor.md_images:
                models.FileImage.objects.create(
                    report=file, file=File(image, image.name), name=image.name
                )

        file.processed = True
        file.save(
            update_fields=[
                "processed",
                "markdown_file",
                "summary",
                "txt2stix_data",
                "ai_describes_incident",
                "ai_incident_summary",
                "ai_incident_classification",
            ]
        )
        job.processed_items += 1
    except CancelledJob:
        msg = f"job cancelled by user for post {post_id}"
        logging.error(msg, exc_info=True)
        job.errors.append(msg)
    except (SoftTimeLimitExceeded, TimeLimitExceeded) as e:
        msg= f"task timed out for post {post_id}: {str(e)}"
        job.errors.append(msg)
        logging.error(msg, exc_info=True)
        job.failed_processes += 1
    except Exception as e:
        msg = f"processing failed for post {post_id}"
        logging.error(msg, exc_info=True)
        job.failed_processes += 1
        job.errors.append(msg)
    job.save(update_fields=["errors", "processed_items", "failed_processes"])
    return job_id


@shared_task
def reindex_pdf_for_post(job_id, post_id):
    post_file = models.File.objects.get(pk=post_id)
    error_msg = None
    success = False
    job = Job.objects.get(pk=job_id)
    if job.is_cancelled():
        return
    job.update_state(models.JobState.PROCESSING)
    feedp = models.FeedProfile.objects.get(feed_id=post_file.feed_id)
    try:
        if not (post_file.profile and post_file.profile.generate_pdf):
            error_msg = f"cannot generate pdf for file {post_id}"
        else:
            pdf_bytes = download_pdf(
                post_file.post.link, cookie_consent_mode=feedp.pdfshift_cookie_settings
            )
            post_file.pdf_file.save(
                f"{post_file.post.title}.pdf", io.BytesIO(pdf_bytes), save=False
            )
            post_file.save(update_fields=["pdf_file"])
            success = True
    except Exception:
        logging.exception(f"process file to pdf failed for {post_file.pk}")
        error_msg = f"process file to pdf failed for {post_file.pk}"

    with transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job_id)
        if success:
            job.processed_items += 1
        else:
            job.failed_processes += 1
            if error_msg:
                job.errors.append(error_msg)
        job.save(
            update_fields=[
                "errors",
                "processed_items",
                "failed_processes",
            ]
        )


from celery import signals


@signals.worker_ready.connect
def mark_old_jobs_as_failed(**kwargs):
    models.Job.objects.filter(state=models.JobState.RETRIEVING).update(
        state=models.JobState.RETRIEVE_FAILED
    )
    models.Job.objects.filter(
        state__in=[
            models.JobState.RETRIEVING,
            models.JobState.QUEUED,
            models.JobState.PROCESSING,
        ]
    ).update(state=models.JobState.CANCELLED)
