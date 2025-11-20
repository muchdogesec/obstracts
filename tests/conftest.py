from datetime import UTC, datetime
import uuid
import pytest
import os
from django.conf import settings
from arango.client import ArangoClient
from pytest_django.fixtures import SettingsWrapper
from pytest_django.lazy_django import skip_if_no_django
from dogesec_commons.stixifier.models import Profile

import pytest
from obstracts.cjob.tasks import create_job_entry
from obstracts.server import models
from history4feed.app import models as h4f_models
from django.utils import timezone


def pytest_sessionstart():
    client = ArangoClient(hosts=settings.ARANGODB_HOST_URL)
    sys_db = client.db(
        "_system",
        username=settings.ARANGODB_USERNAME,
        password=settings.ARANGODB_PASSWORD,
    )
    db_name: str = settings.ARANGODB_DATABASE + "_database"
    if not sys_db.has_database(db_name):
        sys_db.create_database(db_name)
    db = client.db(
        db_name,
        username=settings.ARANGODB_USERNAME,
        password=settings.ARANGODB_PASSWORD,
    )
    for c in db.collections():
        c_name = c["name"]
        if c_name.endswith("_collection"):
            db.collection(c_name).truncate()


@pytest.fixture(autouse=True, scope="session")
def session_settings():
    """A Django settings object which restores changes after the testrun"""
    skip_if_no_django()

    django_settings = SettingsWrapper()
    yield django_settings
    django_settings.finalize()


@pytest.fixture
def stixifier_profile():
    profile = Profile.objects.create(
        name="test-profile",
        extractions=["pattern_host_name"],
        extract_text_from_image=False,
        defang=True,
        relationship_mode="standard",
        ai_settings_relationships=None,
        ai_settings_extractions=[],
        ai_content_check_provider=None,
        ai_create_attack_flow=False,
        id="26fce5ea-c3df-45a2-8989-0225549c704b",
        generate_pdf=True,
    )
    yield profile
    
@pytest.fixture
def stixifier_profile_no_pdf():
    profile = Profile.objects.create(
        name="test-profile-no-pdf",
        extractions=["pattern_host_name"],
        id="a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
        generate_pdf=False,
        defang=False,
    )
    yield profile


@pytest.fixture
def obstracts_job(feed_with_posts, stixifier_profile):
    h4f_job = h4f_models.Job.objects.create(
        feed_id=feed_with_posts.id, id="164716d9-85af-4a81-8f71-9168db3fadf0"
    )
    job = create_job_entry(h4f_job, stixifier_profile.id)
    yield job


@pytest.fixture
def feed_with_posts(stixifier_profile):
    feed = make_feed("6ca6ce37-1c69-4a81-8490-89c91b57e557", stixifier_profile)

    yield feed

def make_feed(feed_id, profile=None):
    h4f_feed = h4f_models.Feed.objects.create(
        title="Reindex Test Feed",
        url="https://example.com/",
        id=feed_id,
    )
    feed: models.FeedProfile = h4f_feed.obstracts_feed


    post1 = h4f_models.Post.objects.create(
        feed=h4f_feed,
        title="Post 1",
        pubdate=datetime(2020, 1, 1, tzinfo=UTC),
        id="561ed102-7584-4b7d-a302-43d4bca5605b",
        link="https://example.blog/1",
    )
    post2 = h4f_models.Post.objects.create(
        feed=h4f_feed,
        title="Post 2",
        pubdate=datetime(2020, 1, 2, tzinfo=UTC),
        id="345c8d0b-c6ca-4419-b1f7-0daeb4e9278b",
        link="https://example.blog/2",
    )
    post3 = h4f_models.Post.objects.create(
        feed=h4f_feed,
        title="Post 3: Royalty",
        pubdate=datetime(2020, 1, 3, tzinfo=UTC),
        id="72e1ad04-8ce9-413d-b620-fe7c75dc0a39",
        link="https://example.blog/3",
        description="blah Post 3 description blah. It's a beautiful day to be king",
    )
    post4 = h4f_models.Post.objects.create(
        feed=h4f_feed,
        title="Post 4",
        pubdate=datetime(2020, 1, 4, tzinfo=UTC),
        id="42a5d042-26fa-41f3-8850-307be3f330cf",
        link="https://example.blog/4",
        description="The execution was so beautiful and royal."
    )
    for post, summary in [(post1, "blank"), (post2, "something very random"), (post3, "this is not so random"), (post4, "die die die, fascists must die")]:
        models.File.objects.create(feed=feed, processed=True, post=post, summary=summary, profile=profile)
    return feed


@pytest.fixture
def feeds():
    return [
        h4f_models.Feed.objects.create(
            url="https://example.com/rss1.xml",
            title="Latest TTPs from APT29 in 2025",
            feed_type="atom",
            description="A technical breakdown of tactics, techniques, and procedures used by APT29, focusing on credential harvesting and living-off-the-land binaries.",
            id=uuid.UUID("6ca6ce37-1c69-4a81-8490-89c91b57e557"),
        ),
        h4f_models.Feed.objects.create(
            url="https://example.com/rss2.xml",
            title="Threat Intelligence with MISP",
            feed_type="rss",
            description="A practical guide on how to use MISP to collect, correlate, and share cyber threat intelligence.",
            id=uuid.UUID("0dfccb58-158c-4436-b338-163e3662943c"),
        ),
        h4f_models.Feed.objects.create(
            url="https://example.com/rss3.xml",
            title="Indicators of Compromise in Financial Sector Attacks",
            feed_type="skeleton",
            id=uuid.UUID("dd3ea54c-3a9d-4f9f-a690-983e2fd8f235"),
            description="Analysis of IOCs observed in recent phishing and ransomware campaigns targeting banks and fintech firms."
        ),
    ]


@pytest.fixture(scope="session")
def api_schema():
    import schemathesis
    from obstracts.asgi import application

    yield schemathesis.openapi.from_asgi("/api/schema/?format=json", application)
