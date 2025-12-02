import itertools
import os
import time
from urllib.parse import urljoin
from dogesec_commons.objects.helpers import ArangoDBHelper
from txt2stix.retriever import STIXObjectRetriever
from obstracts.server.models import FeedProfile, Job

def get_vulnerabilities(collection_name, update_time):
    helper = ArangoDBHelper(collection_name, None)
    binds = {'@collection': collection_name}
    vulnerabilities = helper.execute_query("""
FOR doc IN @@collection
FILTER doc.type == "vulnerability"
COLLECT name = doc.name INTO prim_key = doc._key
RETURN [name, prim_key]
    """, bind_vars=binds, paginate=False)
    vulnerabilities = dict(vulnerabilities)
    retriever = STIXObjectRetriever("vulmatch")
    updates = []
    for chunk in itertools.batched(vulnerabilities, 50):
        chunk = ','.join(chunk)
        for v in retriever._retrieve_objects(urljoin(retriever.api_root, f"v1/cve/objects/?cve_id={chunk}")):
            primary_keys = vulnerabilities[v['name']]
            for _key in primary_keys:
                updates.append({'_key': _key, **v, '_obstract_updated_on': update_time})
    return updates

def run_on_collections(job: Job):
    update_time = time.time()
    db = ArangoDBHelper('', None).db
    feeds = FeedProfile.objects.all()
    for feed in feeds:
        collection_name = feed.vertex_collection
        print(f"Processing {collection_name}")
        updates = get_vulnerabilities(collection_name, update_time)
        if not updates:
            continue
        collection = db.collection(collection_name)
        for chunk in itertools.batched(updates, 500):
            collection.update_many(chunk, raise_on_document_error=True)
            if job:
                job.processed_items += len(chunk)
                job.save(update_fields=['processed_items'])