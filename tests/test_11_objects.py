from datetime import UTC, datetime
import os
import time
from types import SimpleNamespace
import unittest, pytest
from urllib.parse import urljoin
from dateutil.parser import parse as parse_date
import logging

from tests.utils import remove_unknown_keys, wait_for_jobs

base_url = os.environ["SERVICE_BASE_URL"]
import requests

@pytest.mark.parametrize(
        "endpoint",
        [
            "smos",
            "sros",
            "scos",
            "sdos",
        ]
)
def test_paths_no_dup(endpoint):
    url = urljoin(base_url, f'api/v1/objects/{endpoint}/')
    resp = requests.get(url)
    assert resp.status_code == 200, url
    data = resp.json()
    assert data['page_results_count'] <= data['total_results_count']
    object_refs = {obj['id'] for obj in data['objects']}
    dd = [obj['id'] for obj in data['objects']]
    for d in object_refs:
        dd.remove(d)
    assert len(object_refs) == data['page_results_count'], f"data contains duplicate ids: {set(dd)}"

@pytest.mark.parametrize(
    "feed_id",
    [
        "cb0ba709-b841-521a-a3f2-5e1429f4d366",
        "d1d96b71-c687-50db-9d2b-d0092d1d163a",
    ]
)
def test_feed_identity(feed_id):
    feed_url = urljoin(base_url, f'api/v1/feeds/{feed_id}/')
    identity_url = urljoin(base_url, f'api/v1/objects/identity--{feed_id}/')

    resp = requests.get(feed_url)
    assert resp.status_code == 200, "bad feed"

    feed_metadata = resp.json()
    print(identity_url)

    resp = requests.get(identity_url)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data['objects']) == 1, "no identity for feed"
    identity = data['objects'][0]

    assert identity['modified'] == feed_metadata['datetime_modified']
    assert identity['created'] == feed_metadata['datetime_added']
    assert identity['name'] == feed_metadata['title']
    assert identity['description'] == feed_metadata['description']
    assert identity['contact_information'] == feed_metadata['url']
