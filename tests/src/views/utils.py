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



def make_h4f_job(feed: FeedProfile):
    job = h4f_models.Job.objects.create(feed_id=feed.id)
    return job