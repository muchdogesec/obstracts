import logging
import math
from urllib.parse import urljoin
from celery import group, shared_task, chain, chord, current_app, current_task, subtask
from django.conf import settings

from .obstracts_helpers import ObstractsProcessor
from ..server.models import Job, FeedProfile
from ..server import models

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
    logging.info(f"[{job_resp.status_code=}] job_state: {h4f_job}")
    job = Job.objects.get(pk=job_id)
    job.history4feed_status = h4f_job["state"]
    job.item_count = h4f_job["count_of_items"]
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
    print("root and job id ", current_task.request.root_id, current_task.request.id)
    try:
        return poll_once(job_id)
    except BaseException as e:
        logging.exception(e)
        current_task.retry(max_retries=200)


def new_task(feed_dict, profile_id):
    feed, _ = FeedProfile.objects.update_or_create(
        id=feed_dict["id"], title=feed_dict["title"], profile_id=profile_id
    )
    job = Job.objects.create(id=feed_dict["job_id"], feed=feed)
    (poll_job.s(job.id) | start_processing.s(job.id)).apply_async(
        countdown=POLL_INTERVAL, root_id=job.id, task_id=job.id
    )


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
            f"/api/v1/feeds/{job.feed_id}/posts/",
            params={"job_id": job_id, "page": current_page},
        )
        current_page += 1
        if resp.ok:
            data = resp.json()
            posts.extend(data["posts"])
            item_count = data["total_results_count"]
        else:
            logging.error(
                f"got HTTP {resp.status_code} while processing job for {job_id}. body: {resp.text}, count: {len(posts)}"
            )
            break

    logging.info("processing %d posts for job %s", len(posts), job_id)
    tasks = [process_post.si(job_id, post) for post in posts]
    tasks.append(job_completed_with_error.si(job_id))
    return chain(tasks).apply_async()


@shared_task
def set_job_completed(job_id):
    logging.info("job with id %s completed processing", job_id)
    job = Job.objects.get(id=job_id)
    job.state = models.JobState.PROCESSED
    job.save()


@shared_task
def process_post(job_id, post, *args):
    job = Job.objects.get(id=job_id)
    try:
        processor = ObstractsProcessor(post, job)
        processor.process()
        job.processed_items += 1
    except Exception as e:
        logging.error("failed to process post with id: %s", post["id"])
        logging.exception(e)
        job.failed_processes += 1
    job.save()
    return job_id


@current_app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    """ """
    sender.add_periodic_task(settings.CHECK_FOR_NEW_POSTS_MINS * 60, start_automatic_update.s(), name='cron jobs to automatically update feeds every ?? interval')


@shared_task
def start_automatic_update():
    print("Running feed retrieve")
    for feed in FeedProfile.objects.all():
        feed_resp = make_h4f_request(f"/api/v1/feeds/{feed.id}/", method="PATCH")
        feed_dict = feed_resp.json()
        print(feed_dict)
        new_task(feed_dict, feed.profile.id)
