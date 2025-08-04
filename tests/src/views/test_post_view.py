import io
import json
from unittest.mock import patch
import uuid

import pytest
from rest_framework.response import Response
from obstracts.cjob import tasks
from obstracts.server import models
from obstracts.server.models import File
from obstracts.server.views import FeedPostView, MarkdownImageReplacer, PostOnlyView
from dogesec_commons.utils import Pagination, Ordering
from dogesec_commons.utils.filters import MinMaxDateFilter
from obstracts.server.serializers import (
    CreateTaskSerializer,
    ObstractsPostSerializer,
    PostWithFeedIDSerializer,
)
from django_filters.rest_framework import DjangoFilterBackend
from history4feed.app import views as history4feed_views
from django.core.files.uploadedfile import SimpleUploadedFile

from tests.src.views.utils import make_h4f_job
from tests.utils import Transport


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
    assert FeedPostView.serializer_class == PostWithFeedIDSerializer


@pytest.mark.django_db
def test_list_posts(client, feed_with_posts, api_schema):
    with patch.object(
        PostWithFeedIDSerializer,
        "many_init",
        side_effect=PostWithFeedIDSerializer.many_init,
    ) as mock_serializer:
        resp = client.get("/api/v1/posts/")
        assert resp.status_code == 200
        assert resp.data["total_results_count"] == 4, resp.data
        mock_serializer.assert_called_once()  # confirm that we use correct serializer
        api_schema['/api/v1/posts/']['GET'].validate_response(Transport.get_st_response(resp))


@pytest.mark.django_db
def test_retrieve_posts(client, feed_with_posts, api_schema):
    with patch.object(
        PostWithFeedIDSerializer,
        "to_representation",
        autospec=True,
        side_effect=PostWithFeedIDSerializer.to_representation,
    ) as mock_serializer:
        resp = client.get("/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/")
        assert resp.status_code == 200
        assert resp.data["id"] == "561ed102-7584-4b7d-a302-43d4bca5605b"
        mock_serializer.assert_called_once()  # confirm that we use correct serializer
        api_schema['/api/v1/posts/{post_id}/']['GET'].validate_response(Transport.get_st_response(resp))


@pytest.mark.django_db
def test_reindex_post(client, feed_with_posts, stixifier_profile, api_schema):
    payload = {"profile_id": stixifier_profile.id}
    mocked_job = make_h4f_job(feed_with_posts)
    with (
        patch.object(
            PostOnlyView, "new_reindex_post_job", return_value=(None, mocked_job)
        ) as mock_start_h4f_task,
        patch(
            "obstracts.cjob.tasks.create_job_entry", side_effect=tasks.create_job_entry
        ) as mock_create_job_entry,
        patch.object(
            CreateTaskSerializer,
            "is_valid",
            side_effect=CreateTaskSerializer.is_valid,
            autospec=True,
        ) as mock_request_s_class,
    ):
        resp = client.patch(
            "/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/reindex/",
            data=payload,
            content_type="application/json",
        )
        assert resp.status_code == 201, resp.content
        mock_request_s_class.assert_called_once()
        mock_create_job_entry.assert_called_once_with(
            mocked_job, uuid.UUID(str(stixifier_profile.id))
        )
        api_schema['/api/v1/posts/{post_id}/reindex/']['PATCH'].validate_response(Transport.get_st_response(resp))


@pytest.mark.django_db
def test_post_objects(client, feed_with_posts, api_schema):
    with (
        patch.object(
            PostOnlyView,
            "get_post_objects",
            autospec=True,
            side_effect=PostOnlyView.get_post_objects,
        ) as mock_get_post_objects,
    ):
        resp = client.get(
            "/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/objects/",
            data=None,
            content_type="application/json",
        )
        assert resp.status_code == 200, resp.content
        mock_get_post_objects.assert_called_once_with(
            mock_get_post_objects.call_args[0][0],
            "561ed102-7584-4b7d-a302-43d4bca5605b",
        )
        resp.headers['content-type'] = 'application/json'
        
        api_schema['/api/v1/posts/{post_id}/objects/']['GET'].validate_response(Transport.get_st_response(resp))


@pytest.mark.django_db
def test_post_extractions__not_processed(client, feed_with_posts, api_schema):
    post = File.objects.get(post_id="561ed102-7584-4b7d-a302-43d4bca5605b")
    post.txt2stix_data = {"data": "here"}
    post.processed = False
    post.save()
    resp = client.get(
        "/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/extractions/",
        data=None,
        content_type="application/json",
    )
    assert resp.status_code == 404, resp.content
    assert (
        json.loads(resp.content)["details"]["error"]
        == "This post is in failed extraction state, please reindex to access"
    )
    api_schema['/api/v1/posts/{post_id}/extractions/']['GET'].validate_response(Transport.get_st_response(resp))

@pytest.mark.django_db
def test_post_extractions(client, feed_with_posts, api_schema):
    post = File.objects.get(post_id="561ed102-7584-4b7d-a302-43d4bca5605b")
    post.txt2stix_data = {"data": "here"}
    post.save()
    with (
        patch.object(
            PostOnlyView,
            "get_obstracts_file",
            side_effect=PostOnlyView.get_obstracts_file,
            autospec=True,
        ) as mock_get_obstracts_file,
    ):
        resp = client.get(
            "/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/extractions/",
            data=None,
            content_type="application/json",
        )
        assert resp.status_code == 200, resp.content
        mock_get_obstracts_file.assert_called_once()
        assert resp.data == post.txt2stix_data
        api_schema['/api/v1/posts/{post_id}/extractions/']['GET'].validate_response(Transport.get_st_response(resp))


@pytest.mark.django_db
def test_post_extractions_no_data(client, feed_with_posts, api_schema):
    post = File.objects.get(post_id="561ed102-7584-4b7d-a302-43d4bca5605b")

    resp = client.get(
        "/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/extractions/",
        data=None,
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.data == {}
    api_schema['/api/v1/posts/{post_id}/extractions/']['GET'].validate_response(Transport.get_st_response(resp))



@pytest.mark.django_db
def test_post_markdown(client, feed_with_posts):
    post_file = File.objects.get(post_id="561ed102-7584-4b7d-a302-43d4bca5605b")
    post_file.markdown_file.save("markdown.md", io.StringIO("My markdown"))
    images = [
        models.FileImage.objects.create(
            report=post_file, file=SimpleUploadedFile("nb", b"f1"), name="image1"
        ),
        models.FileImage.objects.create(
            report=post_file, file=SimpleUploadedFile("na", b"f2"), name="image2"
        ),
    ]
    with (
        patch.object(
            MarkdownImageReplacer, "get_markdown", return_value="Built Markdown"
        ) as mock_get_markdown,
    ):
        resp = client.get(
            "/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/markdown/",
            data=None,
            content_type="application/json",
        )
        assert resp.status_code == 200, resp.content
        assert resp.headers["content-type"] == "text/markdown"
        assert resp.getvalue() == b"Built Markdown"
        mock_get_markdown.assert_called_once_with(
            "http://testserver/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/markdown/",
            "My markdown",
            {im.name: im.file.url for im in images},
        )


@pytest.mark.django_db
def test_post_images(client, feed_with_posts, api_schema):
    post = File.objects.get(post_id="561ed102-7584-4b7d-a302-43d4bca5605b")
    models.FileImage.objects.create(
        report=post, file=SimpleUploadedFile("nb", b"f1"), name="image1"
    )
    models.FileImage.objects.create(
        report=post, file=SimpleUploadedFile("na", b"f2"), name="image2"
    )

    resp = client.get(
        "/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/images/",
        data=None,
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    assert "images" in resp.data
    assert len(resp.data["images"]) == 2
    api_schema['/api/v1/posts/{post_id}/images/']['GET'].validate_response(Transport.get_st_response(resp))


@pytest.mark.django_db
def test_post_images_no_images(client, feed_with_posts, api_schema):
    post = File.objects.get(post_id="561ed102-7584-4b7d-a302-43d4bca5605b")

    resp = client.get(
        "/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/images/",
        data=None,
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    assert "images" in resp.data
    assert len(resp.data["images"]) == 0
    api_schema['/api/v1/posts/{post_id}/images/']['GET'].validate_response(Transport.get_st_response(resp))

@pytest.mark.django_db
@pytest.mark.parametrize(
    ["text", "expected_ids"],
    [
        ["royal", ["42a5d042-26fa-41f3-8850-307be3f330cf"]],
        ["royalty", ["72e1ad04-8ce9-413d-b620-fe7c75dc0a39"]],
        ["king beautiful", ["72e1ad04-8ce9-413d-b620-fe7c75dc0a39"]],
        ["beauty royalty", ["72e1ad04-8ce9-413d-b620-fe7c75dc0a39"]],
        ["random post", ["345c8d0b-c6ca-4419-b1f7-0daeb4e9278b", "72e1ad04-8ce9-413d-b620-fe7c75dc0a39"]],
        ["-king", ["345c8d0b-c6ca-4419-b1f7-0daeb4e9278b", "42a5d042-26fa-41f3-8850-307be3f330cf", "561ed102-7584-4b7d-a302-43d4bca5605b"]],
    ]
)
def test_search_text(client, feed_with_posts, api_schema, text, expected_ids):
    resp = client.get("/api/v1/posts/", query_params=dict(text=text))
    assert resp.status_code == 200
    assert {r['id'] for r in resp.data['posts']} == set(expected_ids)

@pytest.mark.django_db
def test_post_destroy(client, feed_with_posts, api_schema):
    post = File.objects.get(post_id="561ed102-7584-4b7d-a302-43d4bca5605b")
    with (
        patch.object(
            PostOnlyView, "remove_report_objects", autospec=True
        ) as mock_remove_report_objects,
    ):
        resp = client.delete("/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/")
        assert resp.status_code == 204, resp.content
        resp = client.get("/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/")
        assert resp.status_code == 404
        mock_remove_report_objects.assert_called_once_with(post)
        api_schema['/api/v1/posts/{post_id}/']['DELETE'].validate_response(Transport.get_st_response(resp))
        with pytest.raises(File.DoesNotExist):
            File.objects.get(post_id="561ed102-7584-4b7d-a302-43d4bca5605b")


@pytest.mark.django_db
def test_create_post_in_feed(client, feed_with_posts, stixifier_profile, api_schema):
    payload = {
        "profile_id": stixifier_profile.id,
        "posts": [],
    }
    mocked_job = make_h4f_job(feed_with_posts)
    with (
        patch.object(
            FeedPostView, "new_create_post_job", return_value=mocked_job
        ) as mock_start_h4f_task,
        patch(
            "obstracts.cjob.tasks.create_job_entry", side_effect=tasks.create_job_entry
        ) as mock_create_job_entry,
        patch.object(
            CreateTaskSerializer,
            "is_valid",
            side_effect=CreateTaskSerializer.is_valid,
            autospec=True,
        ) as mock_request_s_class_is_valid,
    ):
        resp = client.post(
            f"/api/v1/feeds/{feed_with_posts.id}/posts/",
            data=payload,
            content_type="application/json",
        )
        assert resp.status_code == 201, resp.content
        request = mock_start_h4f_task.call_args[0][0]
        mock_start_h4f_task.assert_called_once_with(
            request, uuid.UUID(str(feed_with_posts.id))
        )
        mock_request_s_class_is_valid.assert_called_once()
        mock_create_job_entry.assert_called_once_with(
            mocked_job, uuid.UUID(str(stixifier_profile.id))
        )
        api_schema['/api/v1/feeds/{feed_id}/posts/']['POST'].validate_response(Transport.get_st_response(resp))


@pytest.mark.django_db
def test_reindex_posts_in_feed(client, feed_with_posts, stixifier_profile, api_schema):
    payload = {"profile_id": stixifier_profile.id}
    mocked_job = make_h4f_job(feed_with_posts)
    with (
        patch.object(
            FeedPostView, "new_reindex_feed_job", return_value=mocked_job
        ) as mock_start_h4f_task,
        patch(
            "obstracts.cjob.tasks.create_job_entry", side_effect=tasks.create_job_entry
        ) as mock_create_job_entry,
        patch.object(
            CreateTaskSerializer,
            "is_valid",
            side_effect=CreateTaskSerializer.is_valid,
            autospec=True,
        ) as mock_request_s_class,
    ):
        resp = client.patch(
            f"/api/v1/feeds/{feed_with_posts.id}/posts/reindex/",
            data=payload,
            content_type="application/json",
        )
        assert resp.status_code == 201, resp.content
        mock_request_s_class.assert_called_once()
        mock_create_job_entry.assert_called_once_with(
            mocked_job, uuid.UUID(str(stixifier_profile.id))
        )
        api_schema['/api/v1/feeds/{feed_id}/posts/reindex/']['PATCH'].validate_response(Transport.get_st_response(resp))



@pytest.fixture
def list_post_posts(feed_with_posts):
    posts = File.objects.filter(feed=feed_with_posts)

    post1 = posts[0]
    post1.ai_describes_incident = True
    post1.save()

    post3 = posts[2]
    post3.ai_describes_incident = True
    post3.ai_incident_classification = [
        "infostealer",
        "exploit",
        "cyber_crime",
        "indicator_of_compromise",
    ]
    post3.processed = False
    post3.save()

    post4 = posts[3]
    post4.ai_incident_classification = [
        "ransomware",
        "malware",
        "infostealer",
    ]
    post4.ai_describes_incident = False
    post4.save()
    return posts


@pytest.mark.parametrize(
    "filters,expected_ids",
    [
        (
            None,
            [
                "561ed102-7584-4b7d-a302-43d4bca5605b",
                "345c8d0b-c6ca-4419-b1f7-0daeb4e9278b",
                "42a5d042-26fa-41f3-8850-307be3f330cf",
            ],
        ),
        (
            dict(show_hidden_posts=False),
            [
                "561ed102-7584-4b7d-a302-43d4bca5605b",
                "345c8d0b-c6ca-4419-b1f7-0daeb4e9278b",
                "42a5d042-26fa-41f3-8850-307be3f330cf",
            ],
        ),
        (
            dict(show_hidden_posts=True),
            [
                "561ed102-7584-4b7d-a302-43d4bca5605b",
                "345c8d0b-c6ca-4419-b1f7-0daeb4e9278b",
                "72e1ad04-8ce9-413d-b620-fe7c75dc0a39",
                "42a5d042-26fa-41f3-8850-307be3f330cf",
            ],
        ),
        (
            dict(ai_describes_incident="false"),
            ["42a5d042-26fa-41f3-8850-307be3f330cf"],
        ),
        (
            dict(ai_describes_incident="true"),
            [
                "561ed102-7584-4b7d-a302-43d4bca5605b",
            ],
        ),
        (
            dict(
                show_hidden_posts=True,
                ai_incident_classification=["ransomware", "cyber_crime"],
            ),
            [
                "72e1ad04-8ce9-413d-b620-fe7c75dc0a39",
                "42a5d042-26fa-41f3-8850-307be3f330cf",
            ],
        ),
        (
            dict(ai_incident_classification=["ransomware", "cyber_crime"]),
            [
                "42a5d042-26fa-41f3-8850-307be3f330cf",
            ],
        ),
    ],
)
@pytest.mark.django_db
def test_list_posts_filter(client, api_schema, list_post_posts, filters, expected_ids):
    resp = client.get("/api/v1/posts/", query_params=filters)
    assert resp.status_code == 200, resp.content
    assert {post["id"] for post in resp.data["posts"]} == set(expected_ids)
    assert resp.data["total_results_count"] == len(expected_ids)
    api_schema["/api/v1/posts/"]["GET"].validate_response(
        Transport.get_st_response(resp)
    )


@pytest.mark.django_db
def test_list_attack_navigator__not_processed(client, feed_with_posts, api_schema):
    post = File.objects.get(post_id="561ed102-7584-4b7d-a302-43d4bca5605b")
    post.txt2stix_data = {"navigator_layer": []}
    post.processed = False
    post.save()
    resp = client.get(
        "/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/attack-navigator/",
        data=None,
        content_type="application/json",
    )
    assert resp.status_code == 404, resp.content
    assert (
        json.loads(resp.content)["details"]["error"]
        == "This post is in failed extraction state, please reindex to access"
    )
    api_schema["/api/v1/posts/{post_id}/attack-navigator/"]["GET"].validate_response(
        Transport.get_st_response(resp)
    )


@pytest.mark.django_db
@pytest.mark.parametrize("layer", [None, []])
def test_list_attack_navigator__nothing(client, feed_with_posts, layer, api_schema):
    post = File.objects.get(post_id="561ed102-7584-4b7d-a302-43d4bca5605b")
    post.txt2stix_data = {"navigator_layer": layer}
    post.save()
    with (
        patch.object(
            PostOnlyView,
            "get_obstracts_file",
            side_effect=PostOnlyView.get_obstracts_file,
            autospec=True,
        ) as mock_get_obstracts_file,
    ):
        resp = client.get(
            "/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/attack-navigator/",
            data=None,
            content_type="application/json",
        )
        assert resp.status_code == 200, resp.content
        mock_get_obstracts_file.assert_called_once()
        assert resp.data == {"ics": False, "mobile": False, "enterprise": False}
        api_schema["/api/v1/posts/{post_id}/attack-navigator/"][
            "GET"
        ].validate_response(Transport.get_st_response(resp))


@pytest.mark.django_db
def test_list_attack_navigator__has_data(client, feed_with_posts, api_schema, navigator_data):
    post = File.objects.get(post_id="561ed102-7584-4b7d-a302-43d4bca5605b")
    post.txt2stix_data = {
        "navigator_layer": navigator_data
    }
    post.save()
    with (
        patch.object(
            PostOnlyView,
            "get_obstracts_file",
            side_effect=PostOnlyView.get_obstracts_file,
            autospec=True,
        ) as mock_get_obstracts_file,
    ):
        resp = client.get(
            "/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/attack-navigator/",
            data=None,
            content_type="application/json",
        )
        assert resp.status_code == 200, resp.content
        mock_get_obstracts_file.assert_called_once()
        assert resp.data == {"ics": True, "mobile": True, "enterprise": False}
        api_schema["/api/v1/posts/{post_id}/attack-navigator/"][
            "GET"
        ].validate_response(Transport.get_st_response(resp))


@pytest.mark.django_db
def test_retrieve_attack_navigator__no_data(client, feed_with_posts, api_schema):
    post = File.objects.get(post_id="561ed102-7584-4b7d-a302-43d4bca5605b")
    post.txt2stix_data = {}
    post.save()
    with (
        patch.object(
            PostOnlyView,
            "get_obstracts_file",
            side_effect=PostOnlyView.get_obstracts_file,
            autospec=True,
        ) as mock_get_obstracts_file,
    ):
        resp = client.get(
            "/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/attack-navigator/ics/",
            data=None,
            content_type="application/json",
        )
        assert resp.status_code == 404, resp.content
        json.loads(resp.content) == {
            "code": 404,
            "details": {"error": "no navigator for this domain", "domains": []},
            "message": "Not Found",
        }
        mock_get_obstracts_file.assert_called_once()
        api_schema["/api/v1/posts/{post_id}/attack-navigator/{attack_domain}/"][
            "GET"
        ].validate_response(Transport.get_st_response(resp))


@pytest.fixture
def navigator_data():
    return [
        {
            "version": "4.5",
            "name": "Basic ICS Layer",
            "domain": "ics-attack",
            "description": "A simple example ICS layer using only required fields.",
            "techniques": [{"techniqueID": "T0887"}, {"techniqueID": "T0853"}],
        },
        {
            "version": "4.5",
            "name": "Minimal Mobile Layer",
            "domain": "mobile-attack",
            "description": "A basic mobile layer with minimal configuration.",
            "techniques": [{"techniqueID": "T1406"}, {"techniqueID": "T1475"}],
        },
    ]


@pytest.mark.django_db
def test_retrieve_attack_navigator__has_data(
    client, feed_with_posts, api_schema, navigator_data
):
    post = File.objects.get(post_id="561ed102-7584-4b7d-a302-43d4bca5605b")
    post.txt2stix_data = {"navigator_layer": navigator_data}
    post.save()

    resp = client.get(
        f"/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/attack-navigator/ics/",
        data=None,
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.data == {
        "version": "4.5",
        "name": "Basic ICS Layer",
        "domain": "ics-attack",
        "description": "A simple example ICS layer using only required fields.",
        "techniques": [{"techniqueID": "T0887"}, {"techniqueID": "T0853"}],
    }
    api_schema["/api/v1/posts/{post_id}/attack-navigator/{attack_domain}/"][
        "GET"
    ].validate_response(Transport.get_st_response(resp))

    resp = client.get(
        f"/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/attack-navigator/mobile/",
        data=None,
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.data == {
        "version": "4.5",
        "name": "Minimal Mobile Layer",
        "domain": "mobile-attack",
        "description": "A basic mobile layer with minimal configuration.",
        "techniques": [{"techniqueID": "T1406"}, {"techniqueID": "T1475"}],
    }
    api_schema["/api/v1/posts/{post_id}/attack-navigator/{attack_domain}/"][
        "GET"
    ].validate_response(Transport.get_st_response(resp))

    resp = client.get(
        f"/api/v1/posts/561ed102-7584-4b7d-a302-43d4bca5605b/attack-navigator/enterprise/",
        data=None,
        content_type="application/json",
    )
    assert resp.status_code == 404, resp.content
    assert json.loads(resp.content)["details"] == {
        "error": "no navigator for this domain",
        "domains": ["ics", "mobile"],
    }
    api_schema["/api/v1/posts/{post_id}/attack-navigator/{attack_domain}/"][
        "GET"
    ].validate_response(Transport.get_st_response(resp))
