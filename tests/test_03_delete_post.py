

import os
import time
from types import SimpleNamespace
import unittest, pytest
from urllib.parse import urljoin

from tests.utils import remove_unknown_keys, wait_for_jobs

base_url = os.environ["SERVICE_BASE_URL"]
import requests

@pytest.mark.parametrize(
    ["post_id", "should_fail"],
    [
        ["8f89731d-b9de-5931-9182-5460af59ca84", True], #post does not exist
        ["afef9ebd-2dee-5ab9-be0b-96c2ad83a1bb", False],
        ["afef9ebd-2dee-5ab9-be0b-96c2ad83a1bb", True], #post already deleted
    ]
)
def test_delete_post(post_id, should_fail, subtests):
    post_url = urljoin(base_url, f"api/v1/posts/{post_id}/")
    delete_resp = requests.delete(post_url)

    if should_fail:
        assert delete_resp.status_code == 404, f"delete post request expected to fail: {delete_resp.text}"
        return
    assert delete_resp.status_code == 204, f"unexpected status, body: {delete_resp.text}"


    get_resp = requests.get(post_url)
    assert get_resp.status_code == 404, f"post should already be deleted"

    with subtests.test('test_delete_report_deletes_objects', post_id=post_id):
        does_delete_post_delete_post_objects(post_id)


def does_delete_post_delete_post_objects(post_id):
    time.sleep(2)
    report_id = f"report--{post_id}"
    report_url = urljoin(base_url, f"api/v1/objects/{report_id}/")
    resp = requests.get(report_url)
    assert resp.status_code == 200
    data = resp.json()
    assert data['total_results_count'] == 0, "report should already be deleted"


