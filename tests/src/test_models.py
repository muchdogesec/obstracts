from unittest.mock import MagicMock, patch

import pytest
from obstracts.server import models
from obstracts.server.views import PostOnlyView
from dogesec_commons.utils import Pagination, Ordering
from dogesec_commons.utils.filters import MinMaxDateFilter
from obstracts.server.serializers import PostWithFeedIDSerializer
from django_filters.rest_framework import DjangoFilterBackend
from history4feed.app import models as h4f_models
from datetime import datetime as dt



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
def _test_signals():
    with (
        patch("obstracts.server.models.auto_create_feed") as mock_auto_create_feed,
        patch("obstracts.server.models.auto_update_identity") as mock_auto_update_identity,
    ):
        h4f_feed = h4f_models.Feed.objects.create(title="Example Feed Name (2)", url="https://example.com/2", id="79c488e3-b1c8-40f1-8b8f-2d90e660e47c")

    with (
        patch("obstracts.server.models.auto_create_feed") as mock_auto_create_feed,
        patch("obstracts.server.models.auto_update_identity") as mock_auto_update_identity,
    ):
        h4f_feed = h4f_models.Feed.objects.create(title="Example Feed Name (1)", url="https://example.com/1", id="42f8adc7-ef3f-4b14-92e7-e388e8bc13c8")
        mock_auto_update_identity.assert_called_once_with(models.FeedProfile, h4f_feed.obstracts_feed)