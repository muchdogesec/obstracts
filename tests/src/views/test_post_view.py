import io
from unittest.mock import patch
import uuid

import pytest
from rest_framework.response import Response
from obstracts.cjob import tasks
from obstracts.server import models
from obstracts.server.models import FeedProfile, File
from obstracts.server.views import FeedPostView, MarkdownImageReplacer, PostOnlyView
from dogesec_commons.utils import Pagination, Ordering
from dogesec_commons.utils.filters import MinMaxDateFilter
from obstracts.server.serializers import CreateTaskSerializer, FetchFeedSerializer, ObstractsPostSerializer, PostWithFeedIDSerializer
from django_filters.rest_framework import DjangoFilterBackend
from history4feed.app import models as h4f_models
from history4feed.app import views as history4feed_views
from django.core.files.uploadedfile import SimpleUploadedFile

from tests.src.views.utils import make_h4f_job


def test_class_variables():
    assert PostOnlyView.serializer_class == PostWithFeedIDSerializer
    assert PostOnlyView.lookup_url_kwarg == "post_id"
    assert PostOnlyView.lookup_field == "id"
    assert PostOnlyView.openapi_tags == ["Posts (by ID)"]

    assert isinstance(PostOnlyView.pagination_class, Pagination)
    assert PostOnlyView.pagination_class.results_key == "posts"
    assert PostOnlyView.filter_backends == [
        DjangoFilterBackend,
        Ordering,
        MinMaxDateFilter,
    ]
    assert PostOnlyView.ordering == "pubdate_descending"
    assert PostOnlyView.ordering_fields == [
        "pubdate",
        "title",
        "datetime_updated",
        "datetime_added",
    ]
    assert history4feed_views.PostOnlyView in PostOnlyView.mro()

    assert history4feed_views.feed_post_view in FeedPostView.mro()
    assert FeedPostView.serializer_class == ObstractsPostSerializer



@pytest.mark.django_db
def test_list_posts(client, feed_with_posts):
    with (
        patch.object(PostWithFeedIDSerializer, 'many_init', side_effect=PostWithFeedIDSerializer.many_init) as mock_serializer
    ):
        resp = client.get('/api/v1/posts/')
        assert resp.status_code == 200
        assert resp.data['total_results_count'] == 4, resp.data
        mock_serializer.assert_called_once() # confirm that we use correct serializer


@pytest.mark.django_db
def test_retrieve_posts(client, feed_with_posts):
    with (
        patch.object(PostWithFeedIDSerializer, 'to_representation') as mock_serializer
    ):
        mock_serializer.return_value = {"some bad data": 1}
        resp = client.get('/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/')
        assert resp.status_code == 200
        assert resp.data == mock_serializer.return_value
        mock_serializer.assert_called_once() # confirm that we use correct serializer

@pytest.mark.django_db
def test_reindex_post(client, feed_with_posts, stixifier_profile):
    payload = {
        "profile_id": stixifier_profile.id
    }
    mocked_job = make_h4f_job(feed_with_posts)
    with (
        patch.object(PostOnlyView, "new_reindex_post_job", return_value=(None, mocked_job)) as mock_start_h4f_task,
        patch("obstracts.cjob.tasks.create_job_entry", side_effect=tasks.create_job_entry) as mock_create_job_entry,
        patch.object(
            CreateTaskSerializer, "is_valid", side_effect=CreateTaskSerializer.is_valid, autospec=True
        ) as mock_request_s_class,
    ):
        resp = client.patch('/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/reindex/', data=payload, content_type="application/json")
        assert resp.status_code == 201, resp.content
        mock_request_s_class.assert_called_once()
        mock_create_job_entry.assert_called_once_with(mocked_job, uuid.UUID(str(stixifier_profile.id)))


@pytest.mark.django_db
def test_post_objects(client, feed_with_posts):
    with (
        patch.object(PostOnlyView, "get_post_objects") as mock_get_post_objects,
    ):
        mock_get_post_objects.return_value=Response()
        resp = client.get('/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/objects/', data=None, content_type="application/json")
        assert resp.status_code == 200, resp.content
        mock_get_post_objects.assert_called_once_with("561ed102-7584-4b7d-a302-43d4bca5605b")

@pytest.mark.django_db
def test_post_extractions(client, feed_with_posts):
    post = File.objects.get(post_id="561ed102-7584-4b7d-a302-43d4bca5605b")
    post.txt2stix_data = {"data": "here"}
    post.save()
    with (
        patch.object(PostOnlyView, "get_obstracts_file", side_effect=PostOnlyView.get_obstracts_file, autospec=True) as mock_get_obstracts_file,
    ):
        resp = client.get('/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/extractions/', data=None, content_type="application/json")
        assert resp.status_code == 200, resp.content
        mock_get_obstracts_file.assert_called_once()
        assert resp.data == post.txt2stix_data


@pytest.mark.django_db
def test_post_extractions_no_data(client, feed_with_posts):
    post = File.objects.get(post_id="561ed102-7584-4b7d-a302-43d4bca5605b")

    resp = client.get('/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/extractions/', data=None, content_type="application/json")
    assert resp.status_code == 200, resp.content
    assert resp.data == {}

@pytest.mark.django_db
def test_post_markdown(client, feed_with_posts):
    with (
        patch.object(MarkdownImageReplacer, "get_markdown", return_value="Built Markdown") as mock_get_markdown,
        patch.object(PostOnlyView, "get_obstracts_file", autospec=True) as mock_get_obstracts_file,
    ):
        resp = client.get('/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/markdown/', data=None, content_type="application/json")
        assert resp.status_code == 200, resp.content
        assert resp.headers['content-type'] == "text/markdown"
        
@pytest.mark.django_db
def test_post_images(client, feed_with_posts):
    post = File.objects.get(post_id="561ed102-7584-4b7d-a302-43d4bca5605b")
    models.FileImage.objects.create(report=post, file=SimpleUploadedFile("nb", b'f1'), name="image1")
    models.FileImage.objects.create(report=post, file=SimpleUploadedFile("na", b'f2'), name="image2")
    
    resp = client.get('/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/images/', data=None, content_type="application/json")
    assert resp.status_code == 200, resp.content
    assert "images" in resp.data
    assert len(resp.data['images']) == 2
        
@pytest.mark.django_db
def test_post_images_no_images(client, feed_with_posts):
    post = File.objects.get(post_id="561ed102-7584-4b7d-a302-43d4bca5605b")
    
    resp = client.get('/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/images/', data=None, content_type="application/json")
    assert resp.status_code == 200, resp.content
    assert "images" in resp.data
    assert len(resp.data['images']) == 0
        
@pytest.mark.django_db
def test_post_destroy(client, feed_with_posts):
    post = File.objects.get(post_id="561ed102-7584-4b7d-a302-43d4bca5605b")
    with (
        patch.object(PostOnlyView, "remove_files", autospec=True) as mock_remove_files,
    ):
        resp = client.delete('/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/')
        assert resp.status_code == 204, resp.content
        resp = client.get('/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/')
        assert resp.status_code == 404
        view = mock_remove_files.call_args[0][0]
        mock_remove_files.assert_called_once_with(view, post)

@pytest.mark.django_db
def test_create_post_in_feed(client, feed_with_posts, stixifier_profile):
    payload = {
        "profile_id": stixifier_profile.id,
        "posts": [],
    }
    mocked_job = make_h4f_job(feed_with_posts)
    with (
        patch.object(FeedPostView, "new_create_post_job", return_value=mocked_job) as mock_start_h4f_task,
        patch("obstracts.cjob.tasks.create_job_entry", side_effect=tasks.create_job_entry) as mock_create_job_entry,
        patch.object(
            CreateTaskSerializer, "is_valid", side_effect=CreateTaskSerializer.is_valid, autospec=True
        ) as mock_request_s_class_is_valid,
    ):
        resp = client.post(f'/api/v1/feeds/{feed_with_posts.id}/posts/', data=payload, content_type="application/json")
        assert resp.status_code == 201, resp.content
        request = mock_start_h4f_task.call_args[0][0]
        mock_start_h4f_task.assert_called_once_with(request, uuid.UUID(str(feed_with_posts.id)))
        mock_request_s_class_is_valid.assert_called_once()
        mock_create_job_entry.assert_called_once_with(mocked_job, uuid.UUID(str(stixifier_profile.id)))

@pytest.mark.django_db
def test_reindex_posts_in_feed(client, feed_with_posts, stixifier_profile):
    payload = {
        "profile_id": stixifier_profile.id
    }
    mocked_job = make_h4f_job(feed_with_posts)
    with (
        patch.object(FeedPostView, "new_reindex_feed_job", return_value=mocked_job) as mock_start_h4f_task,
        patch("obstracts.cjob.tasks.create_job_entry", side_effect=tasks.create_job_entry) as mock_create_job_entry,
        patch.object(
            CreateTaskSerializer, "is_valid", side_effect=CreateTaskSerializer.is_valid, autospec=True
        ) as mock_request_s_class,
    ):
        resp = client.patch(f'/api/v1/feeds/{feed_with_posts.id}/posts/reindex/', data=payload, content_type="application/json")
        assert resp.status_code == 201, resp.content
        mock_request_s_class.assert_called_once()
        mock_create_job_entry.assert_called_once_with(mocked_job, uuid.UUID(str(stixifier_profile.id)))