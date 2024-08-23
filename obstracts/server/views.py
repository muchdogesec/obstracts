import json
from urllib.parse import urljoin
from django.http import HttpResponse
from django.shortcuts import render
from rest_framework import viewsets, decorators, mixins, exceptions
from rest_framework.request import Request
from django.db.models import Model
from drf_spectacular.utils import OpenApiParameter
from .import autoschema as api_schema

from obstracts.server.arango_helpers import ArangoDBHelper
from .utils import (
    MinMaxDateFilter,
    Ordering,
    Pagination,
    Response,
    ErrorResp,
)
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, Filter, BaseCSVFilter
from .serializers import (
    H4fFeedSerializer,
    H4fPostSerializer,
    ProfileSerializer,
    T2SSerializer,
    JobSerializer,
    FeedSerializer,
)
import txt2stix.extractions
import txt2stix.txt2stix
import requests
from django.conf import settings
from drf_spectacular import utils, types
from drf_spectacular.utils import extend_schema, extend_schema_view
from . import models

from ..cjob import tasks


@extend_schema_view(
    list=extend_schema(
        summary="Search profiles",
        description="Profiles determine how txt2stix processes each blog post in a feed. A profile consists of an extractors, aliases, and/or whitelists. You can search for existing profiles here.",
        responses={400: api_schema.DEFAULT_400_ERROR, 200: ProfileSerializer},
    ),
    retrieve=extend_schema(
        summary="Get a profile",
        description="View the configuration of an existing profile. Note, existing profiles cannot be modified.",
        responses={400: api_schema.DEFAULT_400_ERROR, 404: api_schema.DEFAULT_404_ERROR, 200: ProfileSerializer}
    ),
    create=extend_schema(
        summary="Create a new profile",
        description="Add a new Profile that can be applied to new Feeds. A profile consists of an extractors, aliases, and/or whitelists. You can find available extractors, aliases, and whitelists via their respective endpoints. Required fields are name, extractions (at least one extraction ID), relationship_mode (either ai or standard, defines how relationship between extractions should be created), and extract_text_from_image (boolean, defines if image text should be considered for extraction).",
        responses={400: api_schema.DEFAULT_400_ERROR, 200: ProfileSerializer}
    ),
    destroy=extend_schema(
        summary="Delete a profile",
        description="Delete an existing profile. Note, you cannot delete a profile if it is currently being used with an active Feed.",
        responses={404: api_schema.DEFAULT_404_ERROR, 204: None}
    ),
)
class ProfileView(viewsets.ModelViewSet):
    openapi_tags = ["Profiles"]
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


class txt2stixView(mixins.RetrieveModelMixin,
                           mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = T2SSerializer
    lookup_url_kwarg = "id"
    
    def get_queryset(self):
        return None

    @classmethod
    def all_extractors(cls, types):
        retval = {}
        extractors = txt2stix.extractions.parse_extraction_config(
            txt2stix.txt2stix.INCLUDES_PATH
        ).values()
        for extractor in extractors:
            if extractor.type in types:
                retval[extractor.slug] = cls.cleanup_extractor(extractor)
                if extractor.file:
                    retval[extractor.slug]["file"] = urljoin(settings.TXT2STIX_INCLUDE_URL, str(extractor.file.relative_to(txt2stix.txt2stix.INCLUDES_PATH)))
        return retval
    
    @classmethod
    def cleanup_extractor(cls, dct: dict):
        KEYS = ["name", "type", "description", "notes", "file", "created", "modified", "created_by", "version", "stix_mapping"]
        retval = {"id": dct["slug"]}
        for key in KEYS:
            if key in dct:
                retval[key] = dct[key]
        return retval

    def get_all(self):
        raise NotImplementedError("not implemented")
    

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(list(self.get_all().values()))
        return self.get_paginated_response(page)

    def retrieve(self, request, *args, **kwargs):
        items = self.get_all()
        id_ = self.kwargs.get(self.lookup_url_kwarg)
        print(id_, self.lookup_url_kwarg, self.kwargs)
        item = items.get(id_)
        if not item:
            return ErrorResp(404, "item not found")
        return Response(item)

@extend_schema_view(
    list=extend_schema(
        summary="Search Extractors",
        description="Extractors are what extract the data from the text which is then converted into STIX objects.",
        responses={400: api_schema.DEFAULT_400_ERROR, 200: T2SSerializer},
    ),
    retrieve=extend_schema(
        summary="Get an extractor",
        description="Get a specific Extractor.",
        responses={400: api_schema.DEFAULT_400_ERROR, 404: api_schema.DEFAULT_404_ERROR, 200: T2SSerializer},
    ),
)
class ExtractorsView(txt2stixView):
    openapi_tags = ["Extractors"]
    lookup_url_kwarg = "extractor_id"
    pagination_class = Pagination("extractors")

    def get_all(self):
        return self.all_extractors(["lookup", "pattern", "ai"])

@extend_schema_view(
    list=extend_schema(
        summary="Search for Whitelists",
        description="In many cases files will have IoC extractions that are not malicious. e.g. `google.com` (and thus they don't want them to be extracted). Whitelists provide a list of values to be compared to extractions. If a whitelist value matches an extraction, that extraction is removed. To see the values used in this Whitelist, visit the URL shown as the value for the `file` key",
        responses={400: api_schema.DEFAULT_400_ERROR, 200: T2SSerializer},
    ),
    retrieve=extend_schema(
        summary="Get a whitelist",
        description="Get a specific Whitelist. To see the values used in this Whitelist, visit the URL shown as the value for the `file` key",
        responses={400: api_schema.DEFAULT_400_ERROR, 404: api_schema.DEFAULT_404_ERROR, 200: T2SSerializer},
    ),
)
class WhitelistsView(txt2stixView):
    lookup_url_kwarg = "whitelist_id"
    openapi_tags = ["Whitelists"]
    pagination_class = Pagination("whitelists")

    def get_all(self):
        return self.all_extractors(["whitelist"])

@extend_schema_view(
    list=extend_schema(
        summary="Search for aliases",
        description="Aliases replace strings in the blog post with values defined in the Alias. Aliases are applied before extractions. For example, an alias of `USA` with a value `United States` will change all records of `USA` in the blog post with `United States`. To see the values used in this Alias, visit the URL shown as the value for the `file` key",
        responses={400: api_schema.DEFAULT_400_ERROR, 200: T2SSerializer},
    ),
    retrieve=extend_schema(
        summary="Get an Alias",
        description="Get a specific Alias. To see the values used in this Alias, visit the URL shown as the value for the `file` key",
        responses={400: api_schema.DEFAULT_400_ERROR, 404: api_schema.DEFAULT_404_ERROR, 200: T2SSerializer},
    ),
)
class AliasesView(txt2stixView):
    openapi_tags = ["Aliases"]
    pagination_class = Pagination("aliases")

    lookup_url_kwarg = "alias_id"

    def get_all(self):
        return self.all_extractors(["alias"])

@extend_schema_view(
    list=extend_schema(
        summary="Search for Feeds",
        description="Use this endpoint to get a list of all the feeds you are currently subscribed to. This endpoint is usually used to get the id of feed you want to get blog post data for in a follow up request to the GET Feed Posts endpoints or to get the status of a job related to the Feed in a follow up request to the GET Job endpoint. If you already know the id of the Feed already, you can use the GET Feeds by ID endpoint.",
    ),
    retrieve=extend_schema(
        summary="Get a Feed",
        description="Use this endpoint to get information about a specific feed using its ID. You can search for a Feed ID using the GET Feeds endpoint, if required."
    ),
    create=extend_schema(
        request=FeedSerializer,
        summary="Create a new Feed",
        description="Use this endpoint to create to a new feed. The url value used should be a valid RSS or ATOM feed URL. If it is not valid, the Feed will not be created and an error returned. Generally you should set retrieve_full_text to true. If you are certain the blog you are subscribing to has a full text feed already, you can safely set this to false. If url is already associated with an existing Feed, using it via this endpoint will trigger an update request for the blog. If you want to add the url with new settings, first delete it.",
    ),
    destroy=extend_schema(
        summary="Delete a Feed",
        description="Use this endpoint to delete a feed using its ID. This will delete all posts (items) that belong to the feed and cannot be reversed.",
    ),
)
class FeedView(viewsets.ViewSet):
    lookup_url_kwarg = "feed_id"
    openapi_tags = ["Feeds"]
    serializer_class = H4fFeedSerializer
    pagination_class = Pagination("feeds")



    filter_backends = [DjangoFilterBackend, Ordering, MinMaxDateFilter]
    ordering_fields = [
        "datetime_added",
        "title",
        "url",
        "count_of_posts",
        "earliest_item_pubdate",
        "latest_item_pubdate",
    ]
    ordering = ["-datetime_added"]
    minmax_date_fields = ["earliest_item_pubdate", "latest_item_pubdate"]

    class filterset_class(FilterSet):
        title = Filter(
            label="Filter by the content in feed title. Will search for titles that contain the value entered.",
        )
        description = Filter(
            label="Filter by the content in feed description. Will search for descriptions that contain the value entered.",
        )
        url = Filter(
            label="Filter by the content in a feeds URL. Will search for URLs that contain the value entered.",
        )
        id = BaseCSVFilter(
            label="Filter by feed id(s), comma-separated, e.g 6c6e6448-04d4-42a3-9214-4f0f7d02694e,2bce5b30-7014-4a5d-ade7-12913fe6ac36",
        )

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
    
    @classmethod
    def make_request(cls, request, path):
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

    def create(self, request, *args, **kwargs):
        profile_id = self.parse_profile(request)
        resp = self.make_request(request, "/api/v1/feeds/")
        if resp.status_code == 200:
            out = json.loads(resp.content)
            tasks.new_task(out, profile_id)
        return resp

    def list(self, request, *args, **kwargs):
        return self.make_request(request, "/api/v1/feeds/")

    def retrieve(self, request, *args, **kwargs):
        return self.make_request(
            request, f"/api/v1/feeds/{kwargs.get(self.lookup_url_kwarg)}/"
        )

    def destroy(self, request, *args, **kwargs):
        feed_id = kwargs.get(self.lookup_url_kwarg)
        resp = self.make_request(
            request, f"/api/v1/feeds/{feed_id}/"
        )
        ArangoDBHelper(settings.VIEW_NAME, request).remove_matches(dict(_obstracts_feed_id=feed_id))
        return resp

    # @extend_schema(request=FeedSerializer)
    # def partial_update(self, request, *args, **kwargs):
    #     profile_id = self.parse_profile(request)
    #     resp = self.make_request(
    #         request, f"/api/v1/feeds/{kwargs.get(self.lookup_url_kwarg)}/"
    #     )
    #     if resp.status_code == 200:
    #         out = json.loads(resp.content)
    #         tasks.new_task(out, profile_id)
    #     return resp
    
@extend_schema_view(
    list=extend_schema(
        summary="Search for Posts in a Feed",
        description="Use this endpoint if you want to search through all Posts in a Feed. The response of this endpoint is JSON, and is useful if you're building a custom integration to a downstream tool. If you just want to import the data for this blog into your feed reader use the RSS version of this endpoint.",
    ),
    retrieve=extend_schema(
        summary="Retrieve a post in a Feed",
        description="Use this endpoint if you want to search through all Posts in a Feed. The response of this endpoint is JSON, and is useful if you're building a custom integration to a downstream tool. If you just want to import the data for this blog into your feed reader use the RSS version of this endpoint.",
    ),
) 
class PostView(viewsets.ViewSet):
    serializer_class = H4fPostSerializer
    lookup_url_kwarg = 'post_id'
    openapi_tags = ["Feeds"]

    pagination_class = Pagination("posts")
    filter_backends = [DjangoFilterBackend, Ordering, MinMaxDateFilter]
    ordering_fields = ["pubdate", "title"]
    ordering = ["-pubdate"]
    minmax_date_fields = ["pubdate"]

    class filterset_class(FilterSet):
        title = Filter(
            label="Filter by the content in a posts title. Will search for titles that contain the value entered.",
            lookup_expr="search",
        )
        description = Filter(
            label="Filter by the content in a posts description. Will search for descriptions that contain the value entered.",
            lookup_expr="search",
        )
        job_id = Filter(label="Filter the Post by Job ID the Post was downloaded in.")

    def list(self, request, *args, feed_id=None, **kwargs):
        return FeedView.make_request(
            request, f"/api/v1/feeds/{feed_id}/posts/"
        )
    
    def retrieve(self, request, *args, feed_id=None, post_id=None):
        return FeedView.make_request(
            request, f"/api/v1/feeds/{feed_id}/posts/{post_id}"
        )
    
    @extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters() + [
            OpenApiParameter(name="types", many=True, explode=False, type=str)
        ],
    )
    @decorators.action(detail=True, methods=["GET"])
    def objects(self, request, feed_id=None, post_id=None):
        return ArangoDBHelper(settings.VIEW_NAME, request).get_post_objects(post_id, feed_id)

@extend_schema_view(
    list=extend_schema(
        summary="Search Jobs",
        description="""Jobs track the status of the request to get posts for Feeds. For every new Feed added and every update to a Feed requested a job will be created. The id of a job is printed in the POST and PATCH responses respectively, but you can use this endpoint to search for the id again, if required.""",
        responses={400: api_schema.DEFAULT_400_ERROR, 200: JobSerializer},
    ),
    retrieve=extend_schema(
        summary="Get a Job",
        description="""Using a Job ID you can retrieve information about its state via this endpoint. This is useful to see if a Job to get data is complete, how many posts were imported in the job, or if an error has occurred.""",
        responses={404: api_schema.DEFAULT_404_ERROR, 200: JobSerializer},
    ),
)
class JobView(viewsets.ModelViewSet):
    http_method_names = ["get"]
    serializer_class = JobSerializer
    openapi_tags = ["Jobs"]

    def get_queryset(self):
        return models.Job.objects


def make_h4f_request(path, method="GET", params=None, body=None, headers={}):
    url = urljoin(settings.HISTORY4FEED_URL, path)
    headers["host"] = "localhost"
    return requests.request(method, url, params=params, headers=headers, data=body)




@extend_schema_view(
    scos=extend_schema(
        summary="Get a STIX Cyber Observable Object",
        description="Search for observable objects.",
    ),
    retrieve=extend_schema(
        summary="Get an object",
        description="Get an Object using its ID. You can search for Object IDs using the GET Objects SDO, SCO, or SRO endpoints."
    ),
    sdos=extend_schema(
        summary="Get a STIX Domain Object",
        description="Search for domain objects.",
    ),
    sros=extend_schema(
        summary="Get a STIX Relationship Object",
        description="Search for relationship objects. This endpoint is particularly useful to search what other Objects an SCO or SDO is linked to.",
    ),
)
class ObjectsView(viewsets.ViewSet):

    openapi_tags = ["Objects"]
    lookup_url_kwarg = "id"

    @extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters(),
    )
    @decorators.action(detail=False, methods=["GET"])
    def scos(self, request, *args, **kwargs):
        return ArangoDBHelper(settings.VIEW_NAME, request).get_scos()

    @extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters(),
    )
    @decorators.action(detail=False, methods=["GET"])
    def sdos(self, request, *args, **kwargs):
        return ArangoDBHelper(settings.VIEW_NAME, request).get_sdos()

    @extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters(),
    )
    @decorators.action(detail=False, methods=["GET"])
    def sros(self, request, *args, **kwargs):
        return ArangoDBHelper(settings.VIEW_NAME, request).get_sros()

    @extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters(),
    )
    def retrieve(self, request, *args, **kwargs):
        return ArangoDBHelper(settings.VIEW_NAME, request).get_objects_by_id(
            kwargs.get(self.lookup_url_kwarg)
        )

