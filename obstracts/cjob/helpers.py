import time
from dogesec_commons.objects.helpers import ArangoDBHelper
from obstracts.server.models import FeedProfile, Job
from dogesec_commons.objects.kb_sync import sync


def run_on_collections(job: Job, knowledgebase):
    update_time = time.time()
    feeds = FeedProfile.objects.all()
    if job:
        job.extra = job.extra or {}
        job.extra.update(
            feeds=len(feeds),
            processed_feeds=0,
            unique_objects=0,
        )
        job.save(update_fields=['extra'])
    for feed in feeds:
        collection_name = feed.vertex_collection
        print(f"Processing {collection_name}")
        processed_count, updated_count = sync.run_on_kb_and_collection(collection_name, knowledgebase, update_time=update_time)
        if job:
            job.processed_items += updated_count
            job.extra['processed_feeds'] += 1
            job.extra['unique_objects'] += processed_count
            job.save(update_fields=["processed_items", "extra"])