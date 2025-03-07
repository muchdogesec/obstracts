from datetime import UTC, datetime
import os
import random
import time
from types import SimpleNamespace
import unittest, pytest
from urllib.parse import urljoin
from dateutil.parser import parse as parse_date
import logging

from tests.utils import random_list, remove_unknown_keys, wait_for_jobs

base_url = os.environ["SERVICE_BASE_URL"]
import requests


def post_objects_test(post_id, subtests):
    post_url = urljoin(base_url, f"api/v1/posts/{post_id}/objects/")
    get_resp = requests.get(post_url, params=dict(types="report"))
    assert get_resp.status_code == 200, f"response: {get_resp.text}"
    report_objects = get_resp.json()["objects"]
    assert len(report_objects) == 1, "must return only one report object"
    report_object = report_objects[0]
    assert report_object["type"] == "report", "expected a report object"
    report_object_refs = set(report_object["object_refs"])
    get_resp_all = requests.get(post_url)
    objects_data = get_resp_all.json()
    post_object_refs = {obj["id"] for obj in objects_data["objects"]}
    assert (
        len(post_object_refs) == objects_data["page_results_count"]
    ), "duplicate ids in posts' objects"
    assert (
        objects_data["page_results_count"] == objects_data["total_results_count"]
    ), "please set env.DEFAULT_PAGE_SIZE=10000 on the server, for smoother testing"
    assert post_object_refs.issuperset(
        report_object_refs
    ), "not a superset of report.object_refs"

    invalid_refs = {obj["id"] for obj in objects_data["objects"] if obj.get('relationship_type', '') in ['object', 'object-marking', 'created-by']} #remove embedded refs
    invalid_objects = {obj["id"] for obj in objects_data["objects"] if obj['type'] in ['marking-definition', 'identity']}
    report_id = f"report--{post_id}"
    invalid_objects.add(report_id)
    for obj_ref in random_list(
        [
            id
            for id in post_object_refs.difference(invalid_refs).difference(invalid_objects)
        ],
        k=10,
    ):
        with subtests.test(
            "test_object_retrieve", report_id=report_id, obj_ref=obj_ref
        ):
            object_retrieve_test(obj_ref)

        with subtests.test(
            "test_object_in_report", report_id=report_id, obj_ref=obj_ref
        ):
            object_in_report_test(obj_ref, report_id)

        with subtests.test(
            "test_object_delete_in_report", report_id=report_id, obj_ref=obj_ref
        ):
            object_in_report_delete_test(obj_ref, report_id)


def object_retrieve_test(obj_ref):
    objects_url = urljoin(base_url, f"api/v1/objects/{obj_ref}/")
    resp = requests.get(objects_url)
    assert resp.status_code == 200
    assert len(resp.json()["objects"]) == 1
    assert resp.json()["objects"][0]["id"] == obj_ref


def object_in_report_test(obj_ref, report_id):
    objects_url = urljoin(base_url, f"api/v1/objects/{obj_ref}/reports/")
    resp = requests.get(objects_url)
    assert resp.status_code == 200
    reports = resp.json()["reports"]
    assert len(reports) >= 1
    report_ids = {report["id"] for report in reports}
    assert report_id in report_ids

DELETED_OBJECTS: set[tuple[str, str]] = set()
def object_in_report_delete_test(obj_ref, report_id):
    objects_url = urljoin(base_url, f"api/v1/objects/{obj_ref}/reports/{report_id}/")
    resp = requests.delete(objects_url)
    assert resp.status_code == 204

    DELETED_OBJECTS.add((obj_ref, report_id))

def test_all_posts(subtests):
    post_url = urljoin(base_url, f"api/v1/posts/")
    resp = requests.get(post_url, params=dict(types="report"))
    for post in random_list(resp.json()["posts"], 10):
        post_id = post["id"]
        with subtests.test("test_post_objects", post_id=post_id):
            post_objects_test(post_id, subtests)

def test_deleted_objects_deleted(subtests):
    time.sleep(10)
    for obj_ref, report_id in DELETED_OBJECTS:
        assert obj_ref != report_id
        with subtests.test("test_object_deleted_in_report", obj_ref=obj_ref, report_id=report_id):
            objects_url = urljoin(base_url, f"api/v1/objects/{obj_ref}/reports/")
            resp = requests.get(objects_url)
            assert resp.status_code == 200
            reports = resp.json()["reports"]
            assert report_id not in {
                report["id"] for report in reports
            }, "objects/{obj_ref}/report should not contain report_id"

            objects_url = urljoin(base_url, f"api/v1/objects/{report_id}/")
            resp = requests.get(objects_url)
            assert resp.status_code == 200
            reports = resp.json()["objects"]
            assert len(reports) == 1
            assert (
                obj_ref not in reports[0]["object_refs"]
            ), "report.object_refs should not contain object"

# def test_object_reports(object_id, report_id):
#     pass
