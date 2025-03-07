import os
import time
from types import SimpleNamespace
import unittest, pytest
from urllib.parse import urljoin

from tests.utils import remove_unknown_keys, wait_for_jobs

base_url = os.environ["SERVICE_BASE_URL"]
import requests


DATA = [
    {
        "id": "d1d96b71-c687-50db-9d2b-d0092d1d163a",
        "profile_id": "982c5445-9ff8-513b-919b-b354127830c9",
        "feed_type": "rss",
        "include_remote_blogs": False,
        "url": "https://muchdogesec.github.io/fakeblog123/feeds/rss-feed-encoded.xml",
    },
    {
        "id": "cb0ba709-b841-521a-a3f2-5e1429f4d366",
        "feed_type": "atom",
        "pretty_url": "https://muchdogesec.github.io/fakeblog123/",
        "profile_id": "982c5445-9ff8-513b-919b-b354127830c9",
        "title": "Custom Title",
        "description": "Custom description",
        "include_remote_blogs": False,
        "url": "https://muchdogesec.github.io/fakeblog123/feeds/atom-feed-decoded.xml",
    },
    {
        "id": "121e5557-7277-5aa3-945d-e466c6bf92d5",
        "profile_id": "cbe66e30-c883-519a-a2bf-26aaaf17ae52",
        "title": "Custom Title 2",
        "feed_type": "atom",
        "include_remote_blogs": False,
        "url": "https://muchdogesec.github.io/fakeblog123/feeds/atom-feed-cdata.xml",
    },
    {
        "id": "8f89731d-b9de-5931-9182-5460af59ca84",
        "description": "Custom description 2",
        "profile_id": "cbe66e30-c883-519a-a2bf-26aaaf17ae52",
        "feed_type": "rss",
        "include_remote_blogs": False,
        "url": "https://muchdogesec.github.io/fakeblog123/feeds/rss-feed-decoded.xml",
    },
    {
        "id": "d63dad15-8e23-57eb-80f7-715cedf85f33", # not passed in request
        "feed_type": "skeleton", # not passed in request
        "pretty_url": "https://muchdogesec.github.io/fakeblog123/about/",
        "url": "https://muchdogesec.github.io/fakeblog123/",
        "title": "Skeleton custom Title",
        "description": "Skeleton custom description",
    }
]

all_jobs = dict()

def all_blog_parameters():
    return [
        pytest.param(k["url"], k, k.get("should_fail", False))
            for k in DATA
    ]

def all_job_parameters():
    return [
        pytest.param(k.get('profile_id'), k['id'])
            for k in DATA
    ]
@pytest.mark.parametrize(
        ["url", "blog_data", "should_fail"],
        all_blog_parameters(),
)
def test_add_blog(url, blog_data: dict, should_fail, subtests):
    payload = remove_unknown_keys(blog_data, ["pretty_url", "title", "description", "include_remote_blogs", "url", "profile_id"])

    endpoint = urljoin(base_url, "api/v1/feeds/")

    if blog_data["feed_type"] == "skeleton":
        post_resp = requests.post(urljoin(endpoint, "skeleton/"), json=payload)
    else:
        post_resp = requests.post(endpoint, json=payload)

    if should_fail:
        assert not post_resp.ok, "add feed request expected to fail"
        return

    assert post_resp.status_code == 201, f"request failed: {post_resp.text}"
    post_resp_data = post_resp.json()
    job_id = post_resp_data["id"]
    feed_id = post_resp_data.get("feed_id")
    if feed_id:
        all_jobs[feed_id] = job_id
    else:
        feed_id = job_id

    feed_resp = requests.get(urljoin(base_url, f"api/v1/feeds/{feed_id}/"))
    resp_data = feed_resp.json()
    
    assert feed_id == blog_data["id"]

    if job_profile := post_resp_data.get('profile_id'):
        assert blog_data['profile_id'] == job_profile

    if expected_pretty_url := blog_data.get("pretty_url"):
        assert resp_data["pretty_url"] == expected_pretty_url

    if expected_title := blog_data.get("title"):
        assert resp_data["title"] == expected_title

    if expected_description := blog_data.get("description"):
        assert resp_data["description"] == expected_description

    if expected_feed_type := blog_data.get("feed_type"):
        assert resp_data["feed_type"] == expected_feed_type

    if payload.get('use_search_index'):
        assert resp_data["feed_type"] == "search_index"

@pytest.mark.parametrize(
        ["profile_id", "feed_id"],
        all_job_parameters(),
)
def test_wait_for_jobs_and_test_profile(profile_id, feed_id, subtests):
    if not profile_id:
        return
    assert feed_id in all_jobs
    job_id = all_jobs[feed_id]
    wait_for_jobs(job_id)
    resp = requests.get(urljoin(base_url, f"api/v1/posts/"), params=dict(feed_id=feed_id))
    assert resp.status_code == 200
    for post in resp.json()['posts']:
        assert post['feed_id'] == feed_id
        assert post['profile_id'] == profile_id
