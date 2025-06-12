import io
from unittest.mock import patch
import uuid

import pytest
from rest_framework.response import Response
from obstracts.cjob import tasks
from obstracts.server import models
from obstracts.server.models import FeedProfile, File
from obstracts.server.views import FeedView, FeedView, MarkdownImageReplacer, FeedView
from dogesec_commons.utils import Pagination, Ordering
from dogesec_commons.utils.filters import MinMaxDateFilter
from obstracts.server.serializers import (
    CreateTaskSerializer,
    FeedCreateSerializer,
    FetchFeedSerializer,
    ObstractsPostSerializer,
    PostWithFeedIDSerializer,
)
from django_filters.rest_framework import DjangoFilterBackend
from history4feed.app import models as h4f_models
from history4feed.app import views as history4feed_views
from django.core.files.uploadedfile import SimpleUploadedFile

from tests.src.views.utils import make_h4f_job


def test_class_variables():
    assert FeedView.serializer_class == FeedCreateSerializer

    assert isinstance(FeedView.pagination_class, Pagination)
    assert FeedView.pagination_class.results_key == "feeds"

    assert history4feed_views.FeedView in FeedView.mro()


@pytest.mark.django_db
def test_create(client, feed_with_posts, stixifier_profile):
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


@pytest.mark.django_db
def test_fetch(client, feed_with_posts, stixifier_profile):
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
