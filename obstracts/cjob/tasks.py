import logging
import math
from urllib.parse import urljoin
from celery import shared_task, chain, chord
from django.conf import settings

from .obstracts_helpers import ObstractsProcessor
from ..server.models import Job
from ..server import models

POLL_INTERVAL = 10

import requests

def make_h4f_request(path, method='GET', params=None, body=None, headers={}):
    headers = headers or {}
    try:
        url = urljoin(settings.HISTORY4FEED_URL, path)
        headers['host'] = "localhost"
        resp = requests.request(method, url, params=params, headers=headers, data=body)
        return resp
    except Exception as e:
        logging.exception(e)
        raise

def poll_once(job_id):
    logging.info("polling h4f for job with id = %s", job_id)
    job_resp = make_h4f_request(f"/api/v1/jobs/{job_id}/")
    h4f_job = job_resp.json()
    logging.info(f"[{job_resp.status_code=}] job_state: {h4f_job}")
    job = Job.objects.get(pk=job_id)
    job.h4f_status = h4f_job["state"]
    job.item_count = h4f_job["count_of_items"]
    if job.h4f_status == models.H4FState.SUCCESS:
        job.state = models.JobState.PROCESSING
        job.save()
        start_processing.s(job_id, h4f_job).apply_async()
        return False
    elif job.h4f_status == models.H4FState.FAILED:
        job.state = models.JobState.RETRIEVE_FAILED
        job.save()
        return False
    job.save()
    return True

@shared_task
def poll_job(job_id):
    poll_again = True
    try:
        poll_again = poll_once(job_id)
    except BaseException as e:
        logging.exception(e)
    if poll_again:
        poll_job.s(job_id).apply_async(countdown=POLL_INTERVAL)

def new_task(job_id, feed_id, profile_id):
    Job.objects.create(id=job_id, feed_id=feed_id, profile_id=profile_id)
    poll_job.s(job_id).apply_async(countdown=POLL_INTERVAL)

@shared_task
def start_processing(job_id, h4f_job):
    job = Job.objects.get(id=job_id)
    logging.info(f"processing {job_id=}, {job.feed_id=}")
    posts = []
    current_page = 1
    while len(posts) < job.item_count:
        resp = make_h4f_request(f"/api/v1/feeds/{job.feed_id}/posts/", params={"job_id": job_id, 'page': current_page})
        current_page+=1
        if resp.ok:
            posts.extend(resp.json()["posts"])
        else:
            logging.error(f"got HTTP {resp.status_code} while processing job for {job_id}. body: {resp.text}, count: {len(posts)}")
            break

    logging.info("processing %d posts for job %s", len(posts), job_id)
    if posts:
        tasks = [process_post.si(job_id, post) for post in posts]
        tasks.append(set_job_completed.si(job_id))
        chain(tasks).apply_async()
    else:
        set_job_completed.s(job_id).apply_async()

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
        logging.error("failed to process post with id: %s", post['id'])
        logging.exception(e)
        job.failed_processes += 1
    job.save()
    return job_id

