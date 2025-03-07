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