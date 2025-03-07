from datetime import UTC, datetime
import os
import time
from types import SimpleNamespace
import unittest, pytest
from urllib.parse import urljoin
from dateutil.parser import parse as parse_date

from tests.utils import remove_unknown_keys, wait_for_jobs

base_url = os.environ["SERVICE_BASE_URL"]
import requests
@pytest.mark.parametrize(
        "post_id",
        [
            "58514345-4e10-54c9-8f2c-d81507088079",
            "0b2e3754-eaaa-5c2e-88b0-4929da1f922b",
            "88d01727-eacc-5503-a4df-2f6daeb6b816",
        ]
)

def test_mardkdown_extraction(post_id):
    post_url = urljoin(base_url, f"api/v1/posts/{post_id}/markdown/")
    get_resp = requests.get(post_url)
    assert get_resp.status_code == 200
    assert get_resp.headers['content-type'] == 'text/markdown'