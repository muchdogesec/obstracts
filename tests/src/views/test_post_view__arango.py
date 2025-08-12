from functools import lru_cache
import time
from django.conf import settings
import pytest
from dogesec_commons.objects.helpers import ArangoDBHelper
from stix2arango.stix2arango import Stix2Arango
import contextlib
from obstracts.server.models import File
from obstracts.server.views import PostOnlyView
from tests.utils import Transport
from .arango_data import VERTICES, EDGES

def as_arango2stix_db(db_name):
    if db_name.endswith("_database"):
        return "_".join(db_name.split("_")[:-1])
    return db_name

@pytest.fixture()
def wp_feed(feed_with_posts):
    upload_arango_objects(feed_with_posts.vertex_collection, feed_with_posts.edge_collection)
    return feed_with_posts

def upload_arango_objects(vertex_name, edge_name):
    database = as_arango2stix_db(settings.ARANGODB_DATABASE)

    s2a = Stix2Arango(
        database=database,
        collection=vertex_name,
        file="",
        host_url=settings.ARANGODB_HOST_URL,
    )
    s2a.arango.db.collection(vertex_name).insert_many(VERTICES, overwrite_mode='update', sync=True)
    s2a.arango.db.collection(edge_name).insert_many(EDGES, sync=True, overwrite_mode='update')
    time.sleep(1)
    return

@pytest.mark.parametrize(
    "post_id,filters,expected_ids",
    [
        (
            "345c8d0b-c6ca-4419-b1f7-0daeb4e9278b",
            {},
            [
                "phone-number--34b93960-c9c3-514a-9f8f-74a906d48e9a",
                "autonomous-system--3aa27478-50b5-5ab8-9da9-cdc12b657fff",
                "file--22f8ff52-8f62-5f03-a53a-6f50f54fd74c",
            ],
        ),
        (
            "561ed102-7584-4b7d-a302-43d4bca5605b",
            {},
            [
                "indicator--897de26c-826e-5dfe-9b9c-ca24a284c8e4",
                "relationship--1f7d5320-d4ad-56f4-8385-49b3b9ffcbb1",
                "file--109eb6b5-7257-568b-8a3a-146e343ac867",
                "url--d8e65cab-1aa0-5fbe-a32d-da9187d923f0",
                "directory--67ed4ba2-5da4-5cab-a342-1dbe8066c4bc",
                "ipv6-addr--d263657f-0b4d-5048-8be9-2a0e93eeb859",
                "relationship--embedded",
            ],
        ),
        (
            "561ed102-7584-4b7d-a302-43d4bca5605b",
            dict(ignore_embedded_sro=True),
            [
                "indicator--897de26c-826e-5dfe-9b9c-ca24a284c8e4",
                "relationship--1f7d5320-d4ad-56f4-8385-49b3b9ffcbb1",
                "file--109eb6b5-7257-568b-8a3a-146e343ac867",
                "url--d8e65cab-1aa0-5fbe-a32d-da9187d923f0",
                "directory--67ed4ba2-5da4-5cab-a342-1dbe8066c4bc",
                "ipv6-addr--d263657f-0b4d-5048-8be9-2a0e93eeb859",
            ],
        ),
        (
            "561ed102-7584-4b7d-a302-43d4bca5605b",
            dict(ignore_embedded_sro=False),
            [
                "indicator--897de26c-826e-5dfe-9b9c-ca24a284c8e4",
                "relationship--1f7d5320-d4ad-56f4-8385-49b3b9ffcbb1",
                "file--109eb6b5-7257-568b-8a3a-146e343ac867",
                "url--d8e65cab-1aa0-5fbe-a32d-da9187d923f0",
                "directory--67ed4ba2-5da4-5cab-a342-1dbe8066c4bc",
                "ipv6-addr--d263657f-0b4d-5048-8be9-2a0e93eeb859",
                "relationship--embedded",
            ],
        ),
        (
            "561ed102-7584-4b7d-a302-43d4bca5605b",
            dict(ignore_embedded_sro=True, types="relationship,directory"),
            [
                "relationship--1f7d5320-d4ad-56f4-8385-49b3b9ffcbb1",
                "directory--67ed4ba2-5da4-5cab-a342-1dbe8066c4bc",
            ],
        ),
        ("72e1ad04-8ce9-413d-b620-fe7c75dc0a39", {}, []),
        ("42a5d042-26fa-41f3-8850-307be3f330cf", {}, []),
    ],
)
@pytest.mark.django_db
def test_get_post_objects_filters(
    client, wp_feed, post_id, filters, expected_ids, api_schema
):
    resp = client.get(f"/api/v1/posts/{post_id}/objects/", query_params=filters)
    assert resp.status_code == 200, resp.content
    objects = resp.data["objects"]
    assert len(objects) == resp.data["page_results_count"]
    print("====>", {obj["id"] for obj in objects})
    assert {obj["id"] for obj in objects} == set(expected_ids)
    assert len(objects) == len(expected_ids)
    api_schema['/api/v1/posts/{post_id}/objects/']['GET'].validate_response(Transport.get_st_response(resp))



@pytest.mark.parametrize(
    "post_id",
    [
        "561ed102-7584-4b7d-a302-43d4bca5605b",
        "345c8d0b-c6ca-4419-b1f7-0daeb4e9278b",
    ],
)
@pytest.mark.django_db
def test_remove_report_objects(client, wp_feed, post_id):
    post = File.objects.get(pk=post_id)
    PostOnlyView.remove_report_objects(post)
    for collection_name in [
        wp_feed.edge_collection,
        wp_feed.vertex_collection,
    ]:
        c = ArangoDBHelper("", None).db.collection(collection_name)
        for obj in c.all():
            assert obj.get("_obstracts_post_id") != post_id
