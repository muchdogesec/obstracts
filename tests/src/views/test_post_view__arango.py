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


def as_arango2stix_db(db_name):
    if db_name.endswith("_database"):
        return "_".join(db_name.split("_")[:-1])
    return db_name


@contextlib.contextmanager
def make_s2a_uploads(
    uploads: list[tuple[File, list[dict]]],
    truncate_collection=False,
    database=settings.ARANGODB_DATABASE,
    **kwargs,
):
    database = as_arango2stix_db(database)

    for post_file, objects in uploads:
        s2a = Stix2Arango(
            database=database,
            collection=post_file.feed.collection_name,
            file="",
            host_url=settings.ARANGODB_HOST_URL,
            **kwargs,
        )
        for obj in objects:
            obj.update(
                _obstracts_feed_id=str(post_file.feed.id),
                _obstracts_post_id=str(post_file.pk),
            )
        s2a.run(
            data=dict(type="bundle", id="bundle--" + str(post_file.pk), objects=objects)
        )

    time.sleep(1)
    yield s2a

    if truncate_collection:
        for collection, _ in uploads:
            s2a.arango.db.collection(post_file.feed.vertex_collection).truncate()
            s2a.arango.db.collection(post_file.feed.edge_collection).truncate()


@lru_cache
def upload_arango_objects(feed_id):
    posts = File.objects.filter(feed_id=feed_id).all()
    with make_s2a_uploads(
        [
            (
                posts[0],
                [
                    {
                        "type": "indicator",
                        "spec_version": "2.1",
                        "id": "indicator--897de26c-826e-5dfe-9b9c-ca24a284c8e4",
                        "created_by_ref": "identity--f92e15d9-6afc-5ae2-bb3e-85a1fd83a3b5",
                        "created": "2025-05-30T16:21:11.087135Z",
                        "modified": "2025-05-30T16:21:11.087135Z",
                        "name": "ipv6: 2001:db8:3333:4444:5555:6666:7777:8888",
                        "indicator_types": ["unknown"],
                    },
                    {
                        "type": "ipv6-addr",
                        "spec_version": "2.1",
                        "id": "ipv6-addr--d263657f-0b4d-5048-8be9-2a0e93eeb859",
                        "value": "2001:db8:3333:4444:5555:6666:7777:8888",
                    },
                    {
                        "type": "relationship",
                        "spec_version": "2.1",
                        "id": "relationship--1f7d5320-d4ad-56f4-8385-49b3b9ffcbb1",
                        "created_by_ref": "identity--f92e15d9-6afc-5ae2-bb3e-85a1fd83a3b5",
                        "created": "2025-05-30T16:21:11.087135Z",
                        "modified": "2025-05-30T16:21:11.087135Z",
                        "relationship_type": "detected-using",
                        "description": "2001:db8:3333:4444:5555:6666:7777:8888 can be detected in the STIX pattern ipv6: 2001:db8:3333:4444:5555:6666:7777:8888",
                        "source_ref": "ipv6-addr--d263657f-0b4d-5048-8be9-2a0e93eeb859",
                        "target_ref": "indicator--897de26c-826e-5dfe-9b9c-ca24a284c8e4",
                        "object_marking_refs": [
                            "marking-definition--94868c89-83c2-464b-929b-a1a8aa3c8487",
                            "marking-definition--f92e15d9-6afc-5ae2-bb3e-85a1fd83a3b5",
                        ],
                    },
                    {
                        "type": "url",
                        "spec_version": "2.1",
                        "id": "url--d8e65cab-1aa0-5fbe-a32d-da9187d923f0",
                        "value": "http://3.3.3.3",
                    },
                    {
                        "type": "directory",
                        "spec_version": "2.1",
                        "id": "directory--67ed4ba2-5da4-5cab-a342-1dbe8066c4bc",
                        "path": "C:\\Windows\\System64",
                    },
                    {
                        "type": "file",
                        "spec_version": "2.1",
                        "id": "file--109eb6b5-7257-568b-8a3a-146e343ac867",
                        "hashes": {"SHA-1": "86F7E437FAA5A7FCE15D1DDCB9EAEAEA377667B8"},
                    },
                    {
                        "id": "relationship--embedded",
                        "type": "relationship",
                        "_is_ref": True,
                        "source_ref": "some-ref",
                        "target_ref": "another-ref",
                    },
                ],
            ),
            (
                posts[1],
                [
                    {
                        "type": "file",
                        "spec_version": "2.1",
                        "id": "file--22f8ff52-8f62-5f03-a53a-6f50f54fd74c",
                        "hashes": {
                            "SHA-256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
                        },
                    },
                    {
                        "type": "autonomous-system",
                        "spec_version": "2.1",
                        "id": "autonomous-system--3aa27478-50b5-5ab8-9da9-cdc12b657fff",
                        "number": 15139,
                    },
                    {
                        "type": "phone-number",
                        "spec_version": "2.1",
                        "id": "phone-number--34b93960-c9c3-514a-9f8f-74a906d48e9a",
                        "number": "0044 20836 61177",
                        "country": "GB",
                        "extensions": {
                            "extension-definition--14a97ee2-e666-5ada-a6bd-b7177f79e211": {
                                "extension_type": "new-sco"
                            }
                        },
                    },
                ],
            ),
        ],
        truncate_collection=False,
    ):
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
    client, feed_with_posts, post_id, filters, expected_ids, api_schema
):
    upload_arango_objects(str(feed_with_posts.id))
    resp = client.get(f"/api/v1/posts/{post_id}/objects/", query_params=filters)
    assert resp.status_code == 200, resp.content
    objects = resp.data["objects"]
    assert len(objects) == resp.data["page_results_count"]
    assert {obj["id"] for obj in objects} == set(expected_ids)
    assert len(objects) == len(expected_ids)
    api_schema['/api/v1/posts/{post_id}/objects/']['GET'].is_valid_response(Transport.get_st_response(None, resp))



@pytest.mark.parametrize(
    "post_id",
    [
        "561ed102-7584-4b7d-a302-43d4bca5605b",
        "345c8d0b-c6ca-4419-b1f7-0daeb4e9278b",
    ],
)
@pytest.mark.django_db
def test_remove_report_objects(client, feed_with_posts, post_id):
    upload_arango_objects(str(feed_with_posts.id))
    post = File.objects.get(pk=post_id)
    PostOnlyView.remove_report_objects(post)
    for collection_name in [
        feed_with_posts.edge_collection,
        feed_with_posts.vertex_collection,
    ]:
        c = ArangoDBHelper("", None).db.collection(collection_name)
        for obj in c.all():
            assert obj.get("_obstracts_post_id") != post_id
