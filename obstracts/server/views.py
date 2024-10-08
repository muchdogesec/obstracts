import json
import logging
from textwrap import dedent
from urllib.parse import urljoin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from rest_framework import viewsets, decorators, mixins, exceptions, status, request
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from .import autoschema as api_schema
import arango.database
from .arango_based_views.arango_helpers import OBJECT_TYPES

from obstracts.server.arango_based_views.arango_helpers import ArangoDBHelper
from .utils import (
    MinMaxDateFilter,
    Ordering,
    Pagination,
    Response,
    ErrorResp,
)
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, Filter, BaseCSVFilter, UUIDFilter, CharFilter
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
from drf_spectacular.utils import extend_schema, extend_schema_view
from . import models

from ..cjob import tasks
from obstracts.server import serializers

import textwrap

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
        description=textwrap.dedent(
            """
            Add a new Profile that can be applied to new Feeds. A profile consists of extractors, aliases, and/or whitelists. You can find available extractors, aliases, and whitelists via their respective endpoints.\n\n
            The following key/values are accepted in the body of the request:\n\n
            * `name` (required - must be unique)
            * `extractions` (required - at least one extraction ID): can be obtained from the GET Extractors endpoint. This is a [txt2stix](https://github.com/muchdogesec/txt2stix/) setting.
            * `whitelists` (optional): can be obtained from the GET Whitelists endpoint. This is a [txt2stix](https://github.com/muchdogesec/txt2stix/) setting.
            * `aliases` (optional): can be obtained from the GET Whitelists endpoint. This is a [txt2stix](https://github.com/muchdogesec/txt2stix/) setting.
            * `relationship_mode` (required): either `ai` or `standard`. Required AI provider to be configured if using `ai` mode. This is a [txt2stix](https://github.com/muchdogesec/txt2stix/) setting.
            * `extract_text_from_image` (required - boolean): wether to convert the images found in a blog to text. Requires a Google Vision key to be set. This is a [file2txt](https://github.com/muchdogesec/file2txt) setting.
            * `defang` (required - boolean): wether to defang the observables in the blog. e.g. turns `1.1.1[.]1` to `1.1.1.1` for extraction. This is a [file2txt](https://github.com/muchdogesec/file2txt) setting.\n\n
            You cannot modify a profile once it is created. If you need to make changes, you should create another profile with the changes made.
            """
        ),
        responses={400: api_schema.DEFAULT_400_ERROR, 201: ProfileSerializer}
    ),
    destroy=extend_schema(
        summary="Delete a profile",
        description=textwrap.dedent(
            """Delete an existing profile. Note, we would advise against deleting a Profile because any blogs/posts it has been used in will still refer to this ID. If it is deleted, you will not be able to see the profile settings used. Instead, it is usually better to just recreate a Profile with a new name.
            """
        ),
        responses={404: api_schema.DEFAULT_404_ERROR, 204: None}
    ),
)
class ProfileView(viewsets.ModelViewSet):
    openapi_tags = ["Profiles"]
    serializer_class = ProfileSerializer
    http_method_names = ["get", "post", "delete"]
    pagination_class = Pagination("profiles")
    lookup_url_kwarg = "profile_id"

    ordering_fields = ["name", "created"]
    ordering = "created_descending"
    filter_backends = [DjangoFilterBackend, Ordering]

    class filterset_class(FilterSet):
        name = Filter(
            label="Searches Profiles by their name. Search is wildcard. For example, `ip` will return Profiles with names `ip-extractions`, `ips`, etc.",
            lookup_expr="search"
            )

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
        description=textwrap.dedent(
            """
            Extractors are what extract the data from the text which is then converted into STIX objects.\n\n
            For more information see [txt2stix](https://github.com/muchdogesec/txt2stix/).
            """
        ),
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
        description=textwrap.dedent(
            """
            In many cases files will have IoC extractions that are not malicious. e.g. `google.com` (and thus they don't want them to be extracted). Whitelists provide a list of values to be compared to extractions. If a whitelist value matches an extraction, that extraction is removed. To see the values used in this Whitelist, visit the URL shown as the value for the `file` key.\n\n
            For more information see [txt2stix](https://github.com/muchdogesec/txt2stix/).
            """
        ),
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
        description=textwrap.dedent(
            """
            Aliases replace strings in the blog post with values defined in the Alias. Aliases are applied before extractions. For example, an alias of `USA` with a value `United States` will change all records of `USA` in the blog post with `United States`. To see the values used in this Alias, visit the URL shown as the value for the `file` key\n\n
            For more information see [txt2stix](https://github.com/muchdogesec/txt2stix/).
            """
        ),
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
        description=textwrap.dedent(
            """
            Use this endpoint to get a list of all the feeds you are currently subscribed to. This endpoint is usually used to get the id of feed you want to get blog post data for in a follow up request to the GET Feed Posts endpoints or to get the status of a job related to the Feed in a follow up request to the GET Job endpoint. If you already know the id of the Feed already, you can use the GET Feeds by ID endpoint.
            """
        ),
    ),
    retrieve=extend_schema(
        summary="Get a Feed",
        description=textwrap.dedent(
            """
            Use this endpoint to get information about a specific feed using its ID. You can search for a Feed ID using the GET Feeds endpoint, if required.
            """
        ),
    ),
    create=extend_schema(
        request=FeedSerializer,
        responses={201:JobSerializer},
        summary="Create a new Feed",
        description=textwrap.dedent(
            """
            Use this endpoint to create to a new Feed.\n\n
            The following key/values are accepted in the body of the request:\n\n
            * `url` (required): should be a valid RSS or ATOM feed URL. If it is not valid, the Feed will not be created and an error returned. If the `url` is already associated with an existing Feed, a request to this endpoint will trigger an update request for the blog (you can also use the PATCH Feed endpoint to achieve the same thing). If you want to add the `url` with new settings, first delete the Feed it is associated with.\n\n
            * `profile_id` (required - valid Profile ID): You can view existing Profiles, or generated a new one using the Profiles endpoints. You can update the `profile` used for future posts in a Feed, or reindex Posts using a different `profile_id` later. See the Patch Feed and Patch Post endpoints for more information.\n\n
            * `include_remote_blogs` (required): is a boolean setting and will ask history4feed to ignore any feeds not on the same domain as the URL of the feed. Some feeds include remote posts from other sites (e.g. for a paid promotion). This setting (set to `false` allows you to ignore remote posts that do not use the same domain as the `url` used). Generally you should set `include_remote_blogs` to false. The one exception is when things like feed aggregators (e.g. Feedburner) URLs are used, where the actual blog posts are not on the `feedburner.com` (or whatever) domain. In this case `include_remote_blogs` should be set to `true`.\n\n
            The response will return the Job information responsible for getting the requested data you can track using the `id` returned via the GET Jobs by ID endpoint.
            """
        ),
    ),
    destroy=extend_schema(
        summary="Delete a Feed",
        description="Use this endpoint to delete a feed using its ID. This will delete all posts (items) that belong to the feed in the database and therefore cannot be reversed.",
    ),
    partial_update=extend_schema(
        request=serializers.PatchFeedSerializer,
        responses={201: JobSerializer},
        summary="Update a Feed",
        description=textwrap.dedent(
            """
            Use this endpoint to check for new posts on this blog since the last post time. An update request will immediately trigger a job to get the posts between `latest_item_pubdate` for feed and time you make a request to this endpoint.\n\n
            Note, this endpoint can miss updates that have happened to currently indexed posts (where the RSS or ATOM feed does not report the updated date correctly -- which is actually very common). To solve this issue for currently indexed blog posts, use the Update Post endpoint directly.\n\n
            Whilst it is possible to modify the `profile_id` and `include_remote_blogs` options when updating a Feed we would recommend using the same `profile_id` and `include_remote_blogs` as set originally because. it can becoming confusing quickly managing different settings on a per post basis. Generally it's better to reindex the whole blog using the new setting unless you have a good reason not to.\n\n
            The following key/values are accepted in the body of the request:\n\n
            * `profile_id` (required - valid Profile ID): You get the last `profile_id` used for this feed using the Get Jobs endpoint and feed id. Changing this setting will only apply to posts after the `latest_item_pubdate`.\n\n
            * `include_remote_blogs` (required): You get the last `include_remote_blogs` used for this feed using the Get Jobs endpoint and feed id. Changing this setting will only apply to posts after the `latest_item_pubdate`.\n\n
            The response will return the Job information responsible for getting the requested data you can track using the `id` returned via the GET Jobs by ID endpoint.
            """
        ),
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
        title = CharFilter(
            label="Filter by the content in feed title. Will search for titles that contain the value entered.",
        )
        description = CharFilter(
            label="Filter by the content in feed description. Will search for descriptions that contain the value entered.",
        )
        url = CharFilter(
            label="Filter by the content in a feeds URL. Will search for URLs that contain the value entered.",
        )
        id = BaseCSVFilter(
            label="Filter by feed id(s), comma-separated, e.g `6c6e6448-04d4-42a3-9214-4f0f7d02694e,2bce5b30-7014-4a5d-ade7-12913fe6ac36`",
        )

    @classmethod
    def parse_profile(cls, request):
        try:
            obj = json.loads(request.body)
        except:
            obj = None
        if not isinstance(obj, dict):
            raise exceptions.ValidationError(detail="could not process request body")
        profile_id = obj.get(ProfileView.lookup_url_kwarg)
        try:
            models.Profile.objects.get(pk=profile_id)
        except:
            raise exceptions.ValidationError(detail=f"no profile with id: {profile_id}")
        return profile_id
    
    @classmethod
    def make_request(cls, request, path, request_body=None):
        request_kwargs = {
            "headers": {},
            "method": request.method,
            "body": request_body or request.body,
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
        if resp.status_code == 201:
            out = json.loads(resp.content)
            out['feed_id'] = out['id']
            job = tasks.new_task(out, profile_id)
            return Response(JobSerializer(job).data, status=status.HTTP_201_CREATED)
        return resp

    def list(self, request, *args, **kwargs):
        return self.make_request(request, "/api/v1/feeds/")

    def retrieve(self, request, *args, **kwargs):
        return self.make_request(
            request, f"/api/v1/feeds/{kwargs.get(self.lookup_url_kwarg)}/"
        )

    def delete_collections(self, feed: models.FeedProfile):
        db = ArangoDBHelper(feed.collection_name, self.request).db
        try:
            graph = db.graph(db.name.split('_database')[0]+'_graph')
            graph.delete_edge_definition(feed.collection_name+'_edge_collection', purge=True)
            graph.delete_vertex_collection(feed.collection_name+'_vertex_collection', purge=True)
        except BaseException as e:
            logging.error(f"cannot delete collection `{feed.collection_name}`: {e}")

    def destroy(self, request, *args, **kwargs):
        feed_id = kwargs.get(self.lookup_url_kwarg)
        resp = self.make_request(
            request, f"/api/v1/feeds/{feed_id}/"
        )
        try:
            feed = self.get_feed(feed_id)
            self.delete_collections(feed)
            feed.delete()
        except BaseException as e:
            logging.exception(e)
        return resp
    
    @classmethod
    def get_feed(self, feed_id):
        try:
            feed = models.FeedProfile.objects.get(id=feed_id)
        except Exception as e:
            logging.exception(e)
            raise exceptions.ValidationError(detail=f"no feed with id: {feed_id}")
        return feed

    def partial_update(self, request, *args, **kwargs):
        request_body = request.body
        s = serializers.PatchFeedSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        feed = self.get_feed(kwargs.get(self.lookup_url_kwarg))
        resp = self.make_request(
            request, f"/api/v1/feeds/{kwargs.get(self.lookup_url_kwarg)}/", request_body=request_body
        )
        if resp.status_code == 201:
            out = json.loads(resp.content)
            out['feed_id'] = out['id']
            job = tasks.new_task(out, s.data.get("profile_id", feed.profile.id))
            return Response(JobSerializer(job).data, status=status.HTTP_201_CREATED)
        return resp

@extend_schema_view(
    list=extend_schema(
        summary="Search for Posts in a Feed",
        description=textwrap.dedent(
            """Use this endpoint if you want to search through all Posts in a Feed. The response of this endpoint is JSON, and is useful if you're building a custom integration to a downstream tool. If you just want to import the data for this blog into your feed reader use the RSS version of this endpoint.
            """
        ),
    ),
    retrieve=extend_schema(
        summary="Retrieve a post in a Feed",
        description=textwrap.dedent(
            """
            Use this endpoint if you want to search through all Posts in a Feed. The response of this endpoint is JSON, and is useful if you're building a custom integration to a downstream tool. If you just want to import the data for this blog into your feed reader use the RSS version of this endpoint.
             """
        ),
    ),
    partial_update=extend_schema(
        request=serializers.PatchPostSerializer,
        responses={201:JobSerializer},
        summary="Update a Post in A Feed",
        description=textwrap.dedent(
            """
            Occasionally updates to blog posts are not reflected in RSS and ATOM feeds. To ensure the post stored in the database matches the currently published post you make a request to this endpoint using the Post ID to update it.\n\n
            The following key/values are accepted in the body of the request:\n\n
            * `profile_id` (required - valid Profile ID): You get the last `profile_id` used for this post using the Get Jobs endpoint and post id. Changing the profile will potentially change data extracted from the blog.\n\n
            The response will return the Job information responsible for getting the requested data you can track using the `id` returned via the GET Jobs by ID endpoint.
            """
        ),
    ),
    create=extend_schema(
        request=serializers.PostCreateSerializer,
        responses={201:JobSerializer},
        summary="Backfill a Post into A Feed",
        description=textwrap.dedent(
            """
            This endpoint allows you to add Posts manually to a Feed. This endpoint is designed to ingest posts that are not identified by the Wayback Machine (used by the POST Feed endpoint during ingestion). If the feed you want to add a post to does not already exist, you should first add it using the POST Feed endpoint.\n\n
            The following key/values are accepted in the body of the request:\n\n
            * `profile_id` (required): a valid profile ID to define how the post should be processed.\n\n
            * `link` (required): The URL of the blog post. This is where the content of the post is found.\n\n
            * `pubdate` (required): The date of the blog post in the format `YYYY-MM-DD`. history4feed cannot accurately determine a post date in all cases, so you must enter it manually.\n\n
            * `title` (required):  history4feed cannot accurately determine the title of a post in all cases, so you must enter it manually.\n\n
            * `author` (optional): the value to be stored for the author of the post.
            * `categories` (optional) : the value(s) to be stored for the category of the post. Pass as a list like `["tag1","tag2"]`.\n\n
            The response will return the Job information responsible for getting the requested data you can track using the `id` returned via the GET Jobs by ID endpoint.\n\n
            _Note: We do have a proof-of-concept to scrape a site for all blog post urls, titles, and pubdate called [sitemap2posts](https://github.com/muchdogesec/sitemap2posts) which can help form the request body needed for this endpoint._
            """
        ),
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
        job_id = UUIDFilter(label="Filter the Post by Job ID the Post was downloaded in.")

    def list(self, request, *args, feed_id=None, **kwargs):
        return FeedView.make_request(
            request, f"/api/v1/feeds/{feed_id}/posts/"
        )

    def retrieve(self, request, *args, feed_id=None, post_id=None):
        return FeedView.make_request(
            request, f"/api/v1/feeds/{feed_id}/posts/{post_id}"
        )

    def partial_update(self, request, *args, **kwargs):
        request_body = request.body
        s = serializers.PatchFeedSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        feed_id = kwargs.get(FeedView.lookup_url_kwarg)
        post_id = kwargs.get(self.lookup_url_kwarg)
        feed = FeedView.get_feed(feed_id)
        resp = FeedView.make_request(
            request, f"/api/v1/feeds/{kwargs.get(FeedView.lookup_url_kwarg)}/posts/{post_id}/", request_body=request_body
        )
        if resp.status_code == 201:
            out = json.loads(resp.content)
            out['job_id'] = out['id']
            job = tasks.new_post_patch_task(out, s.data.get("profile_id", feed.profile.id))
            return Response(JobSerializer(job).data, status=status.HTTP_201_CREATED)
        return resp
    
    def create(self, request, *args, **kwargs):
        request_body = request.body
        s = serializers.PatchFeedSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        feed_id = kwargs.get(FeedView.lookup_url_kwarg)
        feed = FeedView.get_feed(feed_id)
        resp = FeedView.make_request(
            request, f"/api/v1/feeds/{kwargs.get(FeedView.lookup_url_kwarg)}/posts/", request_body=request_body
        )
        if resp.status_code == 201:
            out = json.loads(resp.content)
            out['job_id'] = out['id']
            job = tasks.new_post_patch_task(out, s.data.get("profile_id", feed.profile.id))
            return Response(JobSerializer(job).data, status=status.HTTP_201_CREATED)
        return resp

    @extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters()
        + [
            # OpenApiParameter(name="types", many=True, explode=False, enum=OBJECT_TYPES),
            OpenApiParameter(
                "types",
                many=True,
                explode=False,
                description="Filter the results by one or more STIX Object types",
                enum=OBJECT_TYPES,
            ),
            OpenApiParameter(
                "include_txt2stix_notes",
                type=bool,
                default=False,
                description="txt2stix creates 3 STIX note Objects that provide information about the processing job. This data is only really helpful for debugging issues, but not for intelligence sharing. Setting this parameters value to `true` will include these STIX note Objects in the response. Most of the time you want to set this parameter to `false` (the default value).",
            ),
        ],
        summary="Get STIX Objects for a specific Post",
        description="This endpoint will return all objects extracted for a post. If you want more flexibility to filter the objects or search for STIX objects across different Posts, use the Get Object endpoints.",
    )
    @decorators.action(detail=True, methods=["GET"])
    def objects(self, request, feed_id=None, post_id=None):
        return ArangoDBHelper(settings.VIEW_NAME, request).get_post_objects(post_id, feed_id)

    @extend_schema(
        responses=None,
        summary="Get Markdown for specific post",
        description="This endpoint will return Markdown extracted for a post.",
        parameters=[
            OpenApiParameter(
                name="Location",
                type=OpenApiTypes.URI,
                location=OpenApiParameter.HEADER,
                description="redirect location of markdown file",
                response=[301],
            )
        ],
    )
    @decorators.action(detail=True, methods=["GET"])
    def markdown(self, request, feed_id=None, post_id=None):
        obj = get_object_or_404(models.File, post_id=post_id)
        return redirect(obj.markdown_file.url, permanent=True)
    
    @extend_schema(
            responses={200: serializers.ImageSerializer(many=True), 404: api_schema.DEFAULT_404_ERROR, 400: api_schema.DEFAULT_400_ERROR},
            filters=False,
            summary="Retrieve images found in a Post",
            description="A local copy of all images is stored on the server. This endpoint lists the image files found in the Post selected.",
    )
    @decorators.action(detail=True, pagination_class=Pagination("images"))
    def images(self, request, feed_id=None, post_id=None, image=None):
        queryset = models.FileImage.objects.filter(report__post_id=post_id).order_by('name')
        paginator = Pagination('images')

        page = paginator.paginate_queryset(queryset, request, self)

        if page is not None:
            serializer = serializers.ImageSerializer(page, many=True, context=dict(request=request))
            return paginator.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)



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
    lookup_url_kwarg = "job_id"
    filter_backends = [DjangoFilterBackend, Ordering]
    ordering_fields = ["created", "item_count"]
    ordering = "created_descending"
    pagination_class = Pagination("jobs")


    class filterset_class(FilterSet):
        feed_id = Filter(
            label="Filter by feed id.",
        )
        state = Filter(
            label="Filter by state.",
        )
        post_id = UUIDFilter(label="Filter by Post ID", method="filter_post_id")

        def filter_post_id(self, qs, field_name, post_id: str):
            jobs = []
            job_count = -1
            page = 1
            while len(jobs) != job_count:
                resp = make_h4f_request("api/v1/jobs", params=dict(post_id=post_id, page=page))
                if not resp.ok:
                    raise serializers.serializers.ValidationError(f"server does not understand this request: {resp.text}")
                data = resp.json()
                jobs.extend((j['id'] for j in data['jobs']))
                job_count = data['total_results_count']
                page += 1
            return qs.filter(id__in=jobs)


    def get_queryset(self):
        return models.Job.objects


def make_h4f_request(path, method="GET", params=None, body=None, headers={}):
    url = urljoin(settings.HISTORY4FEED_URL, path)
    headers["host"] = "localhost"
    return requests.request(method, url, params=params, headers=headers, data=body)
