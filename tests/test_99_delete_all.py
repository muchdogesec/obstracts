import os
import time
from types import SimpleNamespace
import unittest, pytest
from urllib.parse import urljoin

base_url = os.environ["SERVICE_BASE_URL"]
import requests


def get_all_feeds(path):
    if not os.getenv('DELETE_ALL'):
        return []
    resp = requests.get(urljoin(base_url, f"api/v1/{path}/"))
    return [[obj["id"]] for obj in resp.json()[path]]

@pytest.mark.parametrize(
        ["feed_id"],
        get_all_feeds('feeds'),
)
def test_delete_blog(feed_id):
    resp = requests.delete(urljoin(base_url, f"api/v1/feeds/{feed_id}/"))
    assert resp.status_code == 204, "unexpected status code"
    resp = requests.get(urljoin(base_url, f"api/v1/feeds/{feed_id}/"))
    assert resp.status_code == 404, "feed should not exist after deletion"



@pytest.mark.parametrize(
        ["profile_id"],
        get_all_feeds('profiles'),
)
def test_delete_profiles(profile_id):
    resp = requests.delete(urljoin(base_url, f"api/v1/profiles/{profile_id}/"))
    assert resp.status_code == 204, "unexpected status code"
    resp = requests.get(urljoin(base_url, f"api/v1/profiles/{profile_id}/"))
    assert resp.status_code == 404, "feed should not exist after deletion"
