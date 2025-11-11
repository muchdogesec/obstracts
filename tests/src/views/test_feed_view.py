from unittest.mock import patch
import uuid

import pytest
from obstracts.cjob import tasks
from obstracts.server import models
from obstracts.server.views import FeedView, FeedView, FeedView
from dogesec_commons.utils import Pagination
from obstracts.server.serializers import (
    FeedCreateSerializer,
    FetchFeedSerializer,
)
from history4feed.app import views as history4feed_views

from tests.src.views.utils import make_h4f_job

from dogesec_commons.objects.helpers import ArangoDBHelper
from django.conf import settings

from tests.utils import Transport
from rest_framework.test import APIClient


def test_class_variables():
    assert FeedView.serializer_class == FeedCreateSerializer

    assert isinstance(FeedView.pagination_class, Pagination)
    assert FeedView.pagination_class.results_key == "feeds"

    assert history4feed_views.FeedView in FeedView.mro()


@pytest.mark.django_db
def test_create(client, feed_with_posts, stixifier_profile, api_schema):
    job = make_h4f_job(feed_with_posts)

    payload = {
        "profile_id": stixifier_profile.id,
        "title": "",
        "url": "https://example.net/blog",
    }
    mocked_job = make_h4f_job(feed_with_posts)
    with (
        patch.object(
            FeedView, "new_create_job", return_value=mocked_job
        ) as mock_start_h4f_task,
        patch(
            "obstracts.cjob.tasks.create_job_entry", side_effect=tasks.create_job_entry
        ) as mock_create_job_entry,
        patch.object(
            FeedCreateSerializer,
            "is_valid",
            side_effect=FeedCreateSerializer.is_valid,
            autospec=True,
        ) as mock_request_s_class_is_valid,
    ):
        resp = client.post(
            f"/api/v1/feeds/", data=payload, content_type="application/json"
        )
        assert resp.status_code == 201, resp.content
        request = mock_start_h4f_task.call_args[0][0]
        mock_start_h4f_task.assert_called_once_with(request)
        mock_request_s_class_is_valid.assert_called_once()
        mock_create_job_entry.assert_called_once_with(
            mocked_job, uuid.UUID(str(stixifier_profile.id))
        )
        assert resp.data["id"] == str(mocked_job.id)
        api_schema["/api/v1/feeds/"]["POST"].validate_response(
            Transport.get_st_response(resp)
        )


@pytest.mark.django_db
def test_fetch(client, feed_with_posts, stixifier_profile, api_schema):
    payload = {
        "profile_id": stixifier_profile.id,
    }
    mocked_job = make_h4f_job(feed_with_posts)
    with (
        patch.object(
            FeedView, "new_fetch_job", return_value=mocked_job
        ) as mock_start_h4f_task,
        patch(
            "obstracts.cjob.tasks.create_job_entry", side_effect=tasks.create_job_entry
        ) as mock_create_job_entry,
        patch.object(
            FetchFeedSerializer,
            "is_valid",
            side_effect=FetchFeedSerializer.is_valid,
            autospec=True,
        ) as mock_request_s_class_is_valid,
    ):
        resp = client.patch(
            f"/api/v1/feeds/{feed_with_posts.id}/fetch/",
            data=payload,
            content_type="application/json",
        )
        assert resp.status_code == 201, resp.content
        request = mock_start_h4f_task.call_args[0][0]
        mock_start_h4f_task.assert_called_once_with(request)
        mock_request_s_class_is_valid.assert_called_once()
        mock_create_job_entry.assert_called_once_with(
            mocked_job, uuid.UUID(str(stixifier_profile.id))
        )
        assert resp.data["id"] == str(mocked_job.id)
        api_schema["/api/v1/feeds/{feed_id}/fetch/"]["PATCH"].validate_response(
            Transport.get_st_response(resp)
        )


@pytest.mark.django_db
def test_feed_destroy(client, feed_with_posts, api_schema):
    resp = client.delete(f"/api/v1/feeds/{feed_with_posts.id}/")
    assert resp.status_code == 204, resp.content
    helper = ArangoDBHelper(settings.VIEW_NAME, None)
    assert not helper.db.has_collection(
        feed_with_posts.vertex_collection
    ), "vertex collection should already be deleted"
    assert not helper.db.has_collection(
        feed_with_posts.edge_collection
    ), "eddge collection should already be deleted"
    api_schema["/api/v1/feeds/{feed_id}/"]["DELETE"].validate_response(
        Transport.get_st_response(resp)
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ["text", "expected_ids"],
    [
        ["MISP -APT29 -IOC", ["0dfccb58-158c-4436-b338-163e3662943c"]],
        ["phishing or ransomware", ["dd3ea54c-3a9d-4f9f-a690-983e2fd8f235"]],
        [
            "TTP or MISP or IOC",
            [
                "0dfccb58-158c-4436-b338-163e3662943c",
                "dd3ea54c-3a9d-4f9f-a690-983e2fd8f235",
            ],
        ],
    ],
)
def test_search_text(client, feeds, api_schema, text, expected_ids):
    resp = client.get("/api/v1/feeds/", query_params=dict(text=text))
    assert resp.status_code == 200
    assert {r["id"] for r in resp.data["feeds"]} == set(expected_ids)


@pytest.mark.django_db
def test_count_of_post_considers_processed(client, feed_with_posts, rf):
    resp = client.get(f"/api/v1/feeds/{feed_with_posts.pk}/")
    assert resp.status_code == 200
    assert resp.data["count_of_posts"] == 4

    p = models.File.objects.get(pk="42a5d042-26fa-41f3-8850-307be3f330cf")
    p.processed = False
    p.save()
    resp = client.get(f"/api/v1/feeds/{feed_with_posts.pk}/")
    assert resp.status_code == 200
    assert resp.data["count_of_posts"] == 3


@pytest.mark.django_db
def test_reindex_pdfs_for_feed(
    client: APIClient, feed_with_posts, stixifier_profile_no_pdf
):
    # Setup: one post with generate_pdf=True, one with False, one not processed
    all_files = models.File.objects.filter(feed_id=feed_with_posts.id).order_by("pk")

    post_file_2 = all_files[1]
    post_file_2.profile = stixifier_profile_no_pdf
    post_file_2.save()

    post_file_3 = all_files[2]
    post_file_3.processed = False
    post_file_3.save()

    # We expect only 2 files to be reindexed (processed=True, generate_pdf=True)
    path = "/api/v1/feeds/{feed_id}/reindex-pdfs/"
    url = path.format(feed_id=feed_with_posts.id)

    response = client.patch(url)

    with patch(
        "obstracts.cjob.tasks.create_pdf_reindex_job"
    ) as mock_create_reindex_task:
        mock_create_reindex_task.return_value = models.Job.objects.create(
            id=uuid.uuid4(), type=models.JobType.PDF_INDEX, feed=feed_with_posts
        )
        response = client.patch(url)

    mock_create_reindex_task.assert_called_once()

    assert response.status_code == 201
    assert len(mock_create_reindex_task.call_args[0][1]) == 2 # 4 items originally, two removed by the processed==True and generate_pdf==True filters
