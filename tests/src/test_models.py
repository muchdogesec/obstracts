import json
from unittest.mock import MagicMock, patch

from django.conf import settings
import pytest
from obstracts.server import models
from obstracts.server.views import PostOnlyView
from dogesec_commons.utils import Pagination, Ordering
from dogesec_commons.utils.filters import MinMaxDateFilter
from obstracts.server.serializers import PostWithFeedIDSerializer
from django_filters.rest_framework import DjangoFilterBackend
from history4feed.app import models as h4f_models
from datetime import datetime as dt
from dogesec_commons.objects.helpers import ArangoDBHelper



@pytest.mark.django_db
def test_create_feed_adds_collection_name():
    h4f_feed = h4f_models.Feed.objects.create(title="Example Feed-Name", url="https://example.com/", id="fcb679d4-243a-4eca-a58c-f9dc82099d54")
    feed: models.FeedProfile = h4f_feed.obstracts_feed
    assert feed.collection_name == "example_feed_name_fcb679d4243a4ecaa58cf9dc82099d54", "save should generate deterministic collection_name"

    # test that collection_name is never updated even when the title changes
    h4f_feed.title = "A new title"
    feed.save()
    assert feed.collection_name == "example_feed_name_fcb679d4243a4ecaa58cf9dc82099d54", "collection_name should not change on subsequent saves"


@pytest.mark.django_db
def test_feed_generate_collection_name():
    h4f_feed = h4f_models.Feed.objects.create(title="Example Feed Name (2)", url="https://example.com/2", id="79c488e3-b1c8-40f1-8b8f-2d90e660e47c")
    feed: models.FeedProfile = h4f_feed.obstracts_feed
    assert feed.generate_collection_name() == "example_feed_name_2_79c488e3b1c840f18b8f2d90e660e47c"

@pytest.mark.django_db
def test_feed_create_signals():
    with (
        patch("obstracts.server.models.create_collection") as mock_auto_create_collection,
        patch("obstracts.server.models.update_identities") as mock_auto_update_identity,
    ):
        h4f_feed = h4f_models.Feed.objects.create(title="Example Feed Name (2)", url="https://example.com/2", id="79c488e3-b1c8-40f1-8b8f-2d90e660e47c")
        assert h4f_feed.obstracts_feed != None
        mock_auto_create_collection.assert_called_once()
        mock_auto_update_identity.assert_not_called()



@pytest.mark.django_db
def test_create_collection():
    h4f_feed = h4f_models.Feed.objects.create(title="Example Feed Name (2)", url="https://example.com/2", id="79c488e3-b1c8-40f1-8b8f-2d90e660e47c")
    feed: models.FeedProfile = h4f_feed.obstracts_feed
    models.create_collection(feed)
    helper = ArangoDBHelper(settings.VIEW_NAME, None)
    assert helper.db.has_collection(feed.vertex_collection)
    assert helper.db.has_collection(feed.edge_collection)
    for doc in helper.db.collection(feed.vertex_collection).all():
        if doc['id'] == feed.identity['id']:
            assert {k: v for k, v in doc.items() if not k.startswith('_')} == feed.identity_dict, "values must match"
            break
    else:
        raise AssertionError('identity not uploaded')


@pytest.mark.django_db
def test_update_identities():
    h4f_feed = h4f_models.Feed.objects.create(title="Example Feed Name (2)", url="https://example.com/2", id="79c488e3-b1c8-40f1-8b8f-2d90e660e47c")
    feed: models.FeedProfile = h4f_feed.obstracts_feed
    helper = ArangoDBHelper(settings.VIEW_NAME, None)
    with patch.object(models.FeedProfile, "identity_dict", {"name": "Totaly new name", "id": "identity--79c488e3-b1c8-40f1-8b8f-2d90e660e47c"}) as mock_identity:
        models.update_identities(feed)
        for doc in helper.db.collection(feed.vertex_collection).all():
            if doc['id'] == feed.identity['id']:
                print(doc)
                assert doc['name'] == "Totaly new name", "name should have been updated"
                break
        else:
            raise AssertionError('identity not found')
    
@pytest.mark.django_db
def test_feed_modify_signals():
    h4f_feed = h4f_models.Feed.objects.create(title="Example Feed Name (2)", url="https://example.com/2", id="79c488e3-b1c8-40f1-8b8f-2d90e660e47c")
    feed: models.FeedProfile = h4f_feed.obstracts_feed
    with (
        patch("obstracts.server.models.create_collection") as mock_auto_create_collection,
        patch("obstracts.server.models.update_identities") as mock_auto_update_identity,
    ):
        h4f_feed.title = "New title"
        h4f_feed.save()
        mock_auto_create_collection.assert_not_called()
        mock_auto_update_identity.assert_called_once_with(feed)


@pytest.mark.django_db
def test_feed_delete_signals():
    h4f_feed = h4f_models.Feed.objects.create(title="Example Feed Name (2)", url="https://example.com/2", id="79c488e3-b1c8-40f1-8b8f-2d90e660e47c")
    feed: models.FeedProfile = h4f_feed.obstracts_feed
    helper = ArangoDBHelper(settings.VIEW_NAME, None)
    h4f_feed.delete()
    assert not helper.db.has_collection(feed.vertex_collection), "vertex collection should already be deleted"
    assert not helper.db.has_collection(feed.edge_collection), "eddge collection should already be deleted"