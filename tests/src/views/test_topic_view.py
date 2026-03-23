import uuid
from unittest.mock import patch

import pytest

from obstracts.classifier.models import Cluster, DocumentEmbedding
from obstracts.server.models import File
from obstracts.server.topics import TopicDetailSerializer, TopicSerializer, TopicView
from obstracts.server import models as ob_models
from dogesec_commons.utils import Pagination

from tests.utils import Transport

# ── fixtures ──────────────────────────────────────────────────────────────────

CLUSTER_1_ID = uuid.UUID("a1111111-1111-1111-1111-111111111111")
CLUSTER_2_ID = uuid.UUID("a2222222-2222-2222-2222-222222222222")
POST1_ID = uuid.UUID("561ed102-7584-4b7d-a302-43d4bca5605b")
POST2_ID = uuid.UUID("345c8d0b-c6ca-4419-b1f7-0daeb4e9278b")

# 512-dimensional unit vectors
VEC1 = [1.0] + [0.0] * 511
VEC2 = [0.0, 1.0] + [0.0] * 510


@pytest.fixture
def posts_with_clusters(feed_with_posts):
    """Attach DocumentEmbeddings and two Clusters to the first two posts."""
    file1 = File.objects.get(post_id=POST1_ID)
    file2 = File.objects.get(post_id=POST2_ID)

    emb1 = DocumentEmbedding.objects.create(
        id=POST1_ID, text="Iran cyber ops text", embedding=VEC1
    )
    emb2 = DocumentEmbedding.objects.create(
        id=POST2_ID, text="Ransomware overview text", embedding=VEC2
    )

    file1.embedding = emb1
    file1.save(update_fields=["embedding"])
    file2.embedding = emb2
    file2.save(update_fields=["embedding"])

    # cluster1 contains both posts; cluster2 contains only post2
    cluster1 = Cluster.objects.create(
        id=CLUSTER_1_ID,
        label="Iran Cyber Threats",
        description="Iran-aligned cyber operations",
    )
    cluster1.members.set([emb1, emb2])

    cluster2 = Cluster.objects.create(
        id=CLUSTER_2_ID,
        label="Ransomware Campaigns",
        description="Ransomware activity overview",
    )
    cluster2.members.set([emb2])

    return dict(
        feed=feed_with_posts,
        emb1=emb1,
        emb2=emb2,
        cluster1=cluster1,
        cluster2=cluster2,
    )


# ── class-level checks ────────────────────────────────────────────────────────


def test_class_variables():
    assert TopicView.openapi_tags == ["Topics"]
    assert TopicView.lookup_url_kwarg == "topic_id"
    assert isinstance(TopicView.pagination_class, Pagination)
    assert TopicView.pagination_class.results_key == "topics"


# ── list ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_list_topics_empty(client, api_schema):
    resp = client.get("/api/v1/topics/")
    assert resp.status_code == 200
    assert resp.data["total_results_count"] == 0
    assert resp.data["topics"] == []
    api_schema["/api/v1/topics/"]["GET"].validate_response(
        Transport.get_st_response(resp)
    )


@pytest.mark.django_db
def test_list_topics(client, posts_with_clusters, api_schema):
    resp = client.get("/api/v1/topics/")
    assert resp.status_code == 200
    assert resp.data["total_results_count"] == 2
    ids = {t["id"] for t in resp.data["topics"]}
    assert ids == {str(CLUSTER_1_ID), str(CLUSTER_2_ID)}
    api_schema["/api/v1/topics/"]["GET"].validate_response(
        Transport.get_st_response(resp)
    )


@pytest.mark.django_db
def test_list_topics_posts_count(client, posts_with_clusters, api_schema):
    resp = client.get("/api/v1/topics/")
    assert resp.status_code == 200
    by_id = {t["id"]: t for t in resp.data["topics"]}
    # cluster1 has both posts; cluster2 has only post2
    assert by_id[str(CLUSTER_1_ID)]["posts_count"] == 2
    assert by_id[str(CLUSTER_2_ID)]["posts_count"] == 1
    api_schema["/api/v1/topics/"]["GET"].validate_response(
        Transport.get_st_response(resp)
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ["label_query", "expected_ids"],
    [
        ("Iran", [CLUSTER_1_ID]),
        ("ransomware", [CLUSTER_2_ID]),
        ("Cyber", [CLUSTER_1_ID]),  # case-insensitive
        ("campaign", [CLUSTER_2_ID]),  # substring
        ("Threats Campaigns", []),  # no partial-match across words like this
    ],
)
def test_list_topics_label_filter(
    client, posts_with_clusters, api_schema, label_query, expected_ids
):
    resp = client.get("/api/v1/topics/", query_params={"label": label_query})
    assert resp.status_code == 200
    ids = {uuid.UUID(t["id"]) for t in resp.data["topics"]}
    assert ids == set(expected_ids)
    api_schema["/api/v1/topics/"]["GET"].validate_response(
        Transport.get_st_response(resp)
    )


@pytest.mark.django_db
def test_list_topics_uses_topic_serializer(client, posts_with_clusters, api_schema):
    resp = client.get("/api/v1/topics/")
    assert resp.status_code == 200
    topic = resp.data["topics"][0]
    # TopicSerializer: id, label, description, posts_count
    assert set(topic.keys()) >= {"id", "label", "description", "posts_count"}
    # post_ids should NOT be present on the list response
    assert "post_ids" not in topic
    api_schema["/api/v1/topics/"]["GET"].validate_response(
        Transport.get_st_response(resp)
    )


# ── retrieve ──────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_retrieve_topic(client, posts_with_clusters, api_schema):
    resp = client.get(f"/api/v1/topics/{CLUSTER_1_ID}/")
    assert resp.status_code == 200
    assert resp.data["id"] == str(CLUSTER_1_ID)
    assert resp.data["label"] == "Iran Cyber Threats"
    assert resp.data["description"] == "Iran-aligned cyber operations"
    api_schema[f"/api/v1/topics/{{topic_id}}/"]["GET"].validate_response(
        Transport.get_st_response(resp)
    )


@pytest.mark.django_db
def test_retrieve_topic_post_ids(client, posts_with_clusters, api_schema):
    resp = client.get(f"/api/v1/topics/{CLUSTER_1_ID}/")
    assert resp.status_code == 200
    assert "posts" in resp.data
    assert {p["id"] for p in resp.data["posts"]} == {str(POST1_ID), str(POST2_ID)}
    assert set(resp.data["posts"][0].keys()) == {"id", "title", "feed_id"}
    api_schema["/api/v1/topics/{topic_id}/"]["GET"].validate_response(
        Transport.get_st_response(resp)
    )

    # cluster2 only has post2
    resp2 = client.get(f"/api/v1/topics/{CLUSTER_2_ID}/")
    assert resp2.status_code == 200
    assert [p["id"] for p in resp2.data["posts"]] == [str(POST2_ID)]
    api_schema["/api/v1/topics/{topic_id}/"]["GET"].validate_response(
        Transport.get_st_response(resp2)
    )


@pytest.mark.django_db
def test_retrieve_topic_uses_detail_serializer(client, posts_with_clusters, api_schema):
    resp = client.get(f"/api/v1/topics/{CLUSTER_1_ID}/")
    assert resp.status_code == 200
    # TopicDetailSerializer adds posts with post metadata.
    assert "posts" in resp.data
    assert resp.data['posts_count'] == 2
    api_schema["/api/v1/topics/{topic_id}/"]["GET"].validate_response(
        Transport.get_st_response(resp)
    )


@pytest.mark.django_db
def test_retrieve_topic_not_found(client, api_schema):
    missing_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    resp = client.get(f"/api/v1/topics/{missing_id}/")
    assert resp.status_code == 404
    api_schema["/api/v1/topics/{topic_id}/"]["GET"].validate_response(
        Transport.get_st_response(resp)
    )


@pytest.mark.django_db
def test_build_embeddings_action(client, celery_always_eager):
    with patch("obstracts.cjob.tasks.build_topic_embeddings.run") as mock_task:
        resp = client.patch("/api/v1/topics/build_embeddings/")
        assert resp.status_code == 201
        data = resp.json()
        job_id = data.get("id")
        assert job_id

        job = ob_models.Job.objects.get(pk=job_id)
        assert job.type == ob_models.JobType.BUILD_EMBEDDINGS
        assert job.state == ob_models.JobState.PROCESSING
        mock_task.assert_called_once_with(uuid.UUID(job_id), force=False)


@pytest.mark.django_db
def test_build_clusters_action(client, celery_always_eager):
    with patch("obstracts.cjob.tasks.build_topic_clusters.run") as mock_task:
        resp = client.patch("/api/v1/topics/build_clusters/")
        assert resp.status_code == 201
        data = resp.json()
        job_id = data.get("id")
        assert job_id

        job = ob_models.Job.objects.get(pk=job_id)
        assert job.type == ob_models.JobType.BUILD_CLUSTERS
        assert job.state == ob_models.JobState.PROCESSING
        mock_task.assert_called_once_with(uuid.UUID(job_id), force=False)


@pytest.mark.django_db
def test_build_embeddings_action_supports_force(client, celery_always_eager):
    with patch("obstracts.cjob.tasks.build_topic_embeddings.run") as mock_task:
        resp = client.patch("/api/v1/topics/build_embeddings/", data={"force": True}, content_type="application/json")
        assert resp.status_code == 201
        job_id = resp.json().get("id")
        assert job_id
        mock_task.assert_called_once_with(uuid.UUID(job_id), force=True)
