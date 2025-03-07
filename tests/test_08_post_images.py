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
        ["post_id", "expected_image_count"],
        [
            ["58514345-4e10-54c9-8f2c-d81507088079", 0],
            ["0b2e3754-eaaa-5c2e-88b0-4929da1f922b", 4],
            ["88d01727-eacc-5503-a4df-2f6daeb6b816", 4],
        ]
)

def test_image_extraction(post_id, expected_image_count):
    post_url = urljoin(base_url, f"api/v1/posts/{post_id}/images/")
    get_resp = requests.get(post_url)
    data = get_resp.json()
    assert data['total_results_count'] == expected_image_count