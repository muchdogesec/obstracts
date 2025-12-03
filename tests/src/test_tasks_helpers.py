import random
import time
from urllib.parse import urlparse, parse_qs
from arango.client import ArangoClient
from django.conf import settings
from unittest.mock import patch
import pytest
import uuid
from dogesec_commons.objects.helpers import ArangoDBHelper

from obstracts.cjob import helpers
from obstracts.server import models as ob_models


@pytest.fixture(autouse=True)
def obstracts_db(feeds, db):
    helper = ArangoDBHelper("", None)
    f1_objects = FAKE_VULNERABILITIES[:4]
    f2_objects = FAKE_VULNERABILITIES[4:]
    print("ll ", f1_objects)
    print(f2_objects)

    print(feeds[1].obstracts_feed.vertex_collection)
    print(feeds[2].obstracts_feed.vertex_collection)
    coll = helper.db.collection(feeds[1].obstracts_feed.vertex_collection).insert_many(
        f1_objects, raise_on_document_error=True
    )
    coll = helper.db.collection(feeds[2].obstracts_feed.vertex_collection).insert_many(
        f2_objects, raise_on_document_error=True
    )
    yield helper.db
    helper.db.collection(feeds[2].obstracts_feed.vertex_collection).truncate()
    helper.db.collection(feeds[1].obstracts_feed.vertex_collection).truncate()

VULNS = [
    ("CVE-2011-2462", "vulnerability--74ebaaf5-7210-5422-94f5-3464d0db6e1a"),
    ("CVE-2015-0816", "vulnerability--0d92bd85-e2f0-51ec-9773-6cf161498e25"),
    ("CVE-2018-15982", "vulnerability--71706d20-55df-5004-b315-7d696842447e"),
    ("CVE-2024-38475", "vulnerability--59a383f8-f6a6-5871-9fe0-75abbdf676c8"),
    ("CVE-2022-26318", "vulnerability--75a5ba93-b53c-5abf-9c88-75846041cffe"),
    ("CVE-2020-7961", "vulnerability--906fd5ca-f2a6-5dfc-8f4a-2b493c3650ac"),
    ("CVE-2020-8515", "vulnerability--def77e14-20ca-557f-9757-cc0c4147dcd3"),
    ("CVE-2020-8644", "vulnerability--0039762d-8523-514e-bce6-3103e1724b4f"),
    ("CVE-2020-25506", "vulnerability--48ac0edb-984a-55e3-94aa-017c696366b5"),
    ("CVE-2020-26919", "vulnerability--0957b9de-2d8b-5f8b-817d-6a34b7b7f10a"),
]
FAKE_VULNERABILITIES = [
    dict(_key="dummy__" + id, name=name, type="vulnerability", id=random.random())
    for name, id in VULNS
]

@pytest.fixture
def fake_retriever():
    def fake_retrieve(url):
        qs = parse_qs(urlparse(url).query)
        cve_list = qs.get("cve_id", [""])[0].split(",") if qs.get("cve_id") else []
        return [
            {"name": name, "dummy": "info", "extra": "extra"}
            for name in cve_list
            if name
        ]

    with patch(
        "obstracts.cjob.helpers.STIXObjectRetriever._retrieve_objects",
        side_effect=fake_retrieve,
    ):
        yield



@pytest.mark.django_db
def test_get_vulnerabilities(obstracts_db, feeds, fake_retriever):
    r1 = helpers.get_vulnerabilities(
        "threat_intelligence_with_misp_0dfccb58158c4436b338163e3662943c_vertex_collection",
        1,
    ) == [
        {
            "_key": "dummy__vulnerability--74ebaaf5-7210-5422-94f5-3464d0db6e1a",
            "name": "CVE-2011-2462",
            "dummy": "info",
            "extra": "extra",
            "_obstract_updated_on": 1,
        },
        {
            "_key": "dummy__vulnerability--0d92bd85-e2f0-51ec-9773-6cf161498e25",
            "name": "CVE-2015-0816",
            "dummy": "info",
            "extra": "extra",
            "_obstract_updated_on": 1,
        },
        {
            "_key": "dummy__vulnerability--71706d20-55df-5004-b315-7d696842447e",
            "name": "CVE-2018-15982",
            "dummy": "info",
            "extra": "extra",
            "_obstract_updated_on": 1,
        },
        {
            "_key": "dummy__vulnerability--59a383f8-f6a6-5871-9fe0-75abbdf676c8",
            "name": "CVE-2024-38475",
            "dummy": "info",
            "extra": "extra",
            "_obstract_updated_on": 1,
        },
    ]
    r2 = helpers.get_vulnerabilities(
        "indicators_of_compromise_in_financial_sector_attacks_dd3ea54c3a9d4f9fa690983e2fd8f235_vertex_collection",
        2764,
    )
    assert r2 == [
        {
            "_key": "dummy__vulnerability--48ac0edb-984a-55e3-94aa-017c696366b5",
            "name": "CVE-2020-25506",
            "dummy": "info",
            "extra": "extra",
            "_obstract_updated_on": 2764,
        },
        {
            "_key": "dummy__vulnerability--0957b9de-2d8b-5f8b-817d-6a34b7b7f10a",
            "name": "CVE-2020-26919",
            "dummy": "info",
            "extra": "extra",
            "_obstract_updated_on": 2764,
        },
        {
            "_key": "dummy__vulnerability--906fd5ca-f2a6-5dfc-8f4a-2b493c3650ac",
            "name": "CVE-2020-7961",
            "dummy": "info",
            "extra": "extra",
            "_obstract_updated_on": 2764,
        },
        {
            "_key": "dummy__vulnerability--def77e14-20ca-557f-9757-cc0c4147dcd3",
            "name": "CVE-2020-8515",
            "dummy": "info",
            "extra": "extra",
            "_obstract_updated_on": 2764,
        },
        {
            "_key": "dummy__vulnerability--0039762d-8523-514e-bce6-3103e1724b4f",
            "name": "CVE-2020-8644",
            "dummy": "info",
            "extra": "extra",
            "_obstract_updated_on": 2764,
        },
        {
            "_key": "dummy__vulnerability--75a5ba93-b53c-5abf-9c88-75846041cffe",
            "name": "CVE-2022-26318",
            "dummy": "info",
            "extra": "extra",
            "_obstract_updated_on": 2764,
        },
    ]
    assert helpers.get_vulnerabilities(feeds[0].obstracts_feed.vertex_collection, 3) == []

@pytest.mark.django_db
def test_run_on_collections(obstracts_db, feeds, fake_retriever):
    job = ob_models.Job.objects.create(
        id=uuid.uuid4(),
        type=ob_models.JobType.SYNC_VULNERABILITIES,
        state=ob_models.JobState.PROCESSING,
    )
    r1 = helpers.run_on_collections(job)
    assert r1 is None
    f = obstracts_db.collection(feeds[1].obstracts_feed.vertex_collection).find(dict(type='vulnerability'))
    assert all(x.get('dummy') == 'info' for x in f)
    assert len(f) == 4
    g = obstracts_db.collection(feeds[2].obstracts_feed.vertex_collection).find(dict(type='vulnerability'))
    assert all(x.get('dummy') == 'info' for x in g)
    assert len(g) == 6
    job.refresh_from_db()
    assert job.processed_items == 10
