import json
from urllib.parse import urljoin
from django.http import HttpResponse
from django.shortcuts import render
from rest_framework import viewsets, decorators, mixins, exceptions
from rest_framework.request import Request

from obstracts.server.arango_helpers import ArangoDBHelper
from .utils import (
    MinMaxDateFilter,
    Ordering,
    Pagination,
    Response,
    ErrorResp,
)
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, Filter
from .serializers import (
    ProfileSerializer,
    T2SSerializer,
    JobSerializer,
    FeedSerializer,
    StixObjectSerializer,
)
import txt2stix.extractions
import txt2stix.txt2stix
import requests
from django.conf import settings
from drf_spectacular import utils, types
from . import models

from ..cjob import tasks


# Create your views here.
class ProfileView(viewsets.ModelViewSet):
    serializer_class = ProfileSerializer
    http_method_names = ["get", "post", "delete"]
    pagination_class = Pagination("profiles")

    ordering_fields = ["name", "created"]
    ordering = "created_descending"
    filter_backends = [DjangoFilterBackend, Ordering]

    class filterset_class(FilterSet):
        name = Filter(label="wildcard search for name property.", lookup_expr="search")

    def get_queryset(self):
        return models.Profile.objects


class ValuesView(viewsets.GenericViewSet):
    serializer_class = T2SSerializer
    lookup_url_kwarg = "id"

    @classmethod
    def all_extractors(cls, types):
        retval = {}
        extractors = txt2stix.extractions.parse_extraction_config(
            txt2stix.txt2stix.INCLUDES_PATH
        ).values()
        for extractor in extractors:
            if extractor.type in types:
                retval[extractor.slug] = dict(
                    id=extractor.slug, name=extractor.name, type=extractor.type
                )
        return retval

    def get_all(self):
        raise NotImplementedError("not implemented")

    def list(self, request, *args, **kwargs):
        items = self.get_all()
        return Response(list(items.values()))

    def retrieve(self, request, *args, **kwargs):
        items = self.get_all()
        id_ = self.kwargs.get(self.lookup_url_kwarg)
        print(id_, self.lookup_url_kwarg, self.kwargs)
        item = items.get(id_)
        if not item:
            return ErrorResp(404, "item not found")
        return Response(item)


@utils.extend_schema_view(tags=["txt2stix"])
class ExtractorsView(ValuesView):
    lookup_url_kwarg = "extractor_id"

    def get_all(self):
        return self.all_extractors(["lookup", "pattern", "ai"])


class WhitelistsView(ValuesView):
    lookup_url_kwarg = "whitelist_id"

    def get_all(self):
        return self.all_extractors(["whitelist"])


class AliasesView(ValuesView):
    lookup_url_kwarg = "alias_id"

    def get_all(self):
        return self.all_extractors(["alias"])


class FeedView(viewsets.ViewSet):
    lookup_url_kwarg = "feed_id"

    def parse_profile(self, request):
        try:
            obj = json.loads(request.body)
        except:
            obj = None
        if not isinstance(obj, dict):
            raise exceptions.ValidationError(detail="could not process request body")
        profile_id = obj.get("profile_id")
        try:
            models.Profile.objects.get(pk=profile_id)
        except:
            raise exceptions.ValidationError(detail=f"no profile with id: {profile_id}")
        return profile_id

    def make_request(self, request, path):
        request_kwargs = {
            "headers": {},
            "method": request.method,
            "body": request.body,
            "params": request.GET.copy(),
        }
        headers = request_kwargs["headers"]
        for key, value in request.META.items():
            if key.startswith("HTTP_") and key != "HTTP_HOST":
                key = "-".join(key.lower().split("_")[1:])
                headers[key] = value
            elif key == "CONTENT_TYPE":
                headers["content-type"] = value

        resp = make_h4f_request(path, **request_kwargs)
        return HttpResponse(
            resp.content,
            status=resp.status_code,
            content_type=resp.headers.get("content-type"),
        )

    @utils.extend_schema(request=FeedSerializer)
    def create(self, request, *args, **kwargs):
        profile_id = self.parse_profile(request)
        resp = self.make_request(request, "/api/v1/feeds/")
        if resp.status_code == 200:
            out = json.loads(resp.content)
            tasks.new_task(out["job_id"], out["id"], profile_id)
        return resp

    def list(self, request, *args, **kwargs):
        return self.make_request(request, "/api/v1/feeds/")

    def retrieve(self, request, *args, **kwargs):
        return self.make_request(
            request, f"/api/v1/feeds/{kwargs.get(self.lookup_url_kwarg)}/"
        )

    def destroy(self, request, *args, **kwargs):
        return self.make_request(
            request, f"/api/v1/feeds/{kwargs.get(self.lookup_url_kwarg)}/"
        )

    @utils.extend_schema(request=FeedSerializer)
    def partial_update(self, request, *args, **kwargs):
        profile_id = self.parse_profile(request)
        resp = self.make_request(
            request, f"/api/v1/feeds/{kwargs.get(self.lookup_url_kwarg)}/"
        )
        if resp.status_code == 200:
            out = json.loads(resp.content)
            tasks.new_task(out["job_id"], out["id"], profile_id)
        return resp

    @decorators.action(detail=True, methods=["GET"])
    def posts(self, request, *args, **kwargs):
        return self.make_request(
            request, f"/api/v1/feeds/{kwargs.get(self.lookup_url_kwarg)}/posts/"
        )


class JobView(viewsets.ModelViewSet):
    http_method_names = ["get"]
    serializer_class = JobSerializer

    def get_queryset(self):
        return models.Job.objects


def make_h4f_request(path, method="GET", params=None, body=None, headers={}):
    url = urljoin(settings.HISTORY4FEED_URL, path)
    headers["host"] = "localhost"
    return requests.request(method, url, params=params, headers=headers, data=body)


class ObjectsView(viewsets.ViewSet):
    
    lookup_url_kwarg = "id"

    @utils.extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters(),
    )
    @decorators.action(detail=False, methods=["GET"])
    def scos(self, request, *args, **kwargs):
        page, count = ArangoDBHelper.get_page_params(request)
        return ArangoDBHelper().get_scos(page, count)

    @utils.extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters(),
    )
    @decorators.action(detail=False, methods=["GET"])
    def sdos(self, request, *args, **kwargs):
        page, count = ArangoDBHelper.get_page_params(request)
        return ArangoDBHelper().get_sdos(page, count)
    
    @utils.extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters(),
    )
    @decorators.action(detail=False, methods=["GET"])
    def sros(self, request, *args, **kwargs):
        page, count = ArangoDBHelper.get_page_params(request)
        return ArangoDBHelper().get_sros(page, count)
    
    @utils.extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters(),
    )
    def retrieve(self, request, *args, **kwargs):
        page, count = ArangoDBHelper.get_page_params(request)
        return ArangoDBHelper().get_objects_by_id(kwargs.get(self.lookup_url_kwarg), page, count)
