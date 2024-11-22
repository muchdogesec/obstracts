import io
import json
import logging
from urllib.parse import urljoin
from django.http import HttpResponse, FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, decorators, exceptions, status, renderers
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes
from .import autoschema as api_schema
from dogesec_commons.objects.helpers import OBJECT_TYPES
import hyperlink

from dogesec_commons.objects.helpers import ArangoDBHelper
from .utils import (
    MinMaxDateFilter,
    Ordering,
    Pagination,
    Response,
)
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, Filter, BaseCSVFilter, UUIDFilter, CharFilter
from .serializers import (
    H4fFeedSerializer,
    H4fPostSerializer,
    JobSerializer,
    FeedSerializer,
)
import txt2stix.txt2stix
import requests
from django.conf import settings
from drf_spectacular.utils import extend_schema, extend_schema_view
from . import models

from ..cjob import tasks
from obstracts.server import serializers
import textwrap

import mistune
from mistune.renderers.markdown import MarkdownRenderer
from mistune.util import unescape

class PlainMarkdownRenderer(renderers.BaseRenderer):
    media_type = "text/markdown"
    format = "text/markdown"

class MarkdownImageReplacer(MarkdownRenderer):
    def __init__(self, request, queryset):
        self.request = request
        self.queryset = queryset
        super().__init__()
    def image(self, token: dict[str, dict], state: mistune.BlockState) -> str:
        src = token['attrs']['url']
        if not hyperlink.parse(src).absolute:
            try:
                token['attrs']['url'] = self.request.build_absolute_uri(self.queryset.get(name=src).file.url)
            except Exception as e:
                pass
        return super().image(token, state)
    
    def codespan(self, token: dict[str, dict], state: mistune.BlockState) -> str:
        token['raw'] = unescape(token['raw'])
        return super().codespan(token, state)

    @classmethod
    def get_markdown(cls, request, md_text, images_qs: 'models.models.BaseManager[models.FileImage]'):
        modify_links = mistune.create_markdown(escape=False, renderer=cls(request, images_qs))
        return modify_links(md_text)

@extend_schema_view(
    list=extend_schema(
        summary="Search for Feeds",
        description=textwrap.dedent(
            """
            Use this endpoint to get a list of all the feeds you are currently subscribed to. This endpoint is usually used to get the id of feed you want to get blog post data for in a follow up request to the GET Feed Posts endpoints or to get the status of a job related to the Feed in a follow up request to the GET Job endpoint. If you already know the id of the Feed already, you can use the GET Feeds by ID endpoint.
            """
        ),
        responses={200: H4fFeedSerializer, 400: api_schema.DEFAULT_400_ERROR}
    ),
    retrieve=extend_schema(
        summary="Get a Feed",
        description=textwrap.dedent(
            """
            Use this endpoint to get information about a specific feed using its ID. You can search for a Feed ID using the GET Feeds endpoint, if required.
            """
        ),
        responses={200: H4fFeedSerializer, 404: api_schema.DEFAULT_404_ERROR, 400: api_schema.DEFAULT_400_ERROR}
    ),
    create=extend_schema(
        request=FeedSerializer,
        responses={201:JobSerializer, 400: api_schema.DEFAULT_400_ERROR},
        summary="Create a new Feed",
        description=textwrap.dedent(
            """
            Use this endpoint to create to a new Feed.

            The following key/values are accepted in the body of the request:

            * `url` (required): should be a valid RSS or ATOM feed URL. If it is not valid, the Feed will not be created and an error returned. If the `url` is already associated with an existing Feed, a request to this endpoint will trigger an update request for the blog (you can also use the PATCH Feed endpoint to achieve the same thing). If you want to add the `url` with new settings, first delete the Feed it is associated with.
            * `profile_id` (required - valid Profile ID): You can view existing Profiles, or generated a new one using the Profiles endpoints. You can update the `profile` used for future posts in a Feed, or reindex Posts using a different `profile_id` later. See the Patch Feed and Patch Post endpoints for more information.
            * `include_remote_blogs` (required): is a boolean setting and will ask history4feed to ignore any feeds not on the same domain as the URL of the feed. Some feeds include remote posts from other sites (e.g. for a paid promotion). This setting (set to `false` allows you to ignore remote posts that do not use the same domain as the `url` used). Generally you should set `include_remote_blogs` to false. The one exception is when things like feed aggregators (e.g. Feedburner) URLs are used, where the actual blog posts are not on the `feedburner.com` (or whatever) domain. In this case `include_remote_blogs` should be set to `true`.
            * `ai_summary_provider` (optional): you can optionally get an AI model to produce a summary of the blog. You must pass the request in format `provider:model`. Currently supported providers are:
                * `openai:`, models e.g.: `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `gpt-4` ([More here](https://platform.openai.com/docs/models))
                * `anthropic:`, models e.g.: `claude-3-5-sonnet-latest`, `claude-3-5-haiku-latest`, `claude-3-opus-latest` ([More here](https://docs.anthropic.com/en/docs/about-claude/models))
                * `gemini:models/`, models: `gemini-1.5-pro-latest`, `gemini-1.5-flash-latest` ([More here](https://ai.google.dev/gemini-api/docs/models/gemini))

            The `id` of a Feed is generated using a UUIDv5. The namespace used is `6c6e6448-04d4-42a3-9214-4f0f7d02694e` (history4feed) and the value used is `<FEED_URL>` (e.g. `https://muchdogesec.github.io/fakeblog123/feeds/rss-feed-encoded.xml` would have the id `d1d96b71-c687-50db-9d2b-d0092d1d163a`). Therefore, you cannot add a URL that already exists, you must first delete it to add it with new settings.

            Each post ID is generated using a UUIDv5. The namespace used is `6c6e6448-04d4-42a3-9214-4f0f7d02694e` (history4feed) and the value used `<FEED_ID>+<POST_URL>+<POST_PUB_TIME (to .000000Z)>` (e.g. `d1d96b71-c687-50db-9d2b-d0092d1d163a+https://muchdogesec.github.io/fakeblog123///test3/2024/08/20/update-post.html+2024-08-20T10:00:00.000000Z` = `22173843-f008-5afa-a8fb-7fc7a4e3bfda`).

            The response will return the Job information responsible for getting the requested data you can track using the `id` returned via the GET Jobs by ID endpoint.
            """
        ),
    ),
    destroy=extend_schema(
        summary="Delete a Feed",
        description=textwrap.dedent(
            """
            Use this endpoint to delete a feed using its ID. This will delete all posts (items) that belong to the feed in the database and therefore cannot be reversed.
            """
        ),
        responses={200: {}, 404: api_schema.DEFAULT_404_ERROR}
    ),
    partial_update=extend_schema(
        request=serializers.PatchFeedSerializer,
        responses={201: JobSerializer, 404: api_schema.DEFAULT_404_ERROR, 400: api_schema.DEFAULT_400_ERROR},
        summary="Update a Feed",
        description=textwrap.dedent(
            """
            Use this endpoint to check for new posts on this blog since the last post time. An update request will immediately trigger a job to get the posts between `latest_item_pubdate` for feed and time you make a request to this endpoint.

            Note, this endpoint can miss updates that have happened to currently indexed posts (where the RSS or ATOM feed does not report the updated date correctly -- which is actually very common). To solve this issue for currently indexed blog posts, use the Update Post endpoint directly.

            Whilst it is possible to modify the `profile_id` and `include_remote_blogs` options when updating a Feed we would recommend using the same `profile_id` and `include_remote_blogs` as set originally because. it can becoming confusing quickly managing different settings on a per post basis. Generally it's better to reindex the whole blog using the new setting unless you have a good reason not to.

            The following key/values are accepted in the body of the request:

            * `profile_id` (required - valid Profile ID): You get the last `profile_id` used for this feed using the Get Jobs endpoint and feed id. Changing this setting will only apply to posts after the `latest_item_pubdate`.
            * `include_remote_blogs` (required): You get the last `include_remote_blogs` used for this feed using the Get Jobs endpoint and feed id. Changing this setting will only apply to posts after the `latest_item_pubdate`.
            * `ai_summary_provider` (optional): you can optionally get an AI model to produce a summary of the blog. You must pass the request in format `provider:model`. Currently supported providers are:
                * `openai:`, models e.g.: `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `gpt-4` ([More here](https://platform.openai.com/docs/models))
                * `anthropic:`, models e.g.: `claude-3-5-sonnet-latest`, `claude-3-5-haiku-latest`, `claude-3-opus-latest` ([More here](https://docs.anthropic.com/en/docs/about-claude/models))
                * `gemini:models/`, models: `gemini-1.5-pro-latest`, `gemini-1.5-flash-latest` ([More here](https://ai.google.dev/gemini-api/docs/models/gemini))

            Each post ID is generated using a UUIDv5. The namespace used is `6c6e6448-04d4-42a3-9214-4f0f7d02694e` (history4feed) and the value used `<FEED_ID>+<POST_URL>+<POST_PUB_TIME (to .000000Z)>` (e.g. `d1d96b71-c687-50db-9d2b-d0092d1d163a+https://muchdogesec.github.io/fakeblog123///test3/2024/08/20/update-post.html+2024-08-20T10:00:00.000000Z` = `22173843-f008-5afa-a8fb-7fc7a4e3bfda`).

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
            label="Filter the content by the `title` of the feed. Will search for titles that contain the value entered. Search is wildcard so `exploit` will match `exploited` and `exploits`.",
        )
        description = CharFilter(
            label="Filter by the content in feed `description`. Will search for descriptions that contain the value entered. Search is wildcard so `exploit` will match `exploited` and `exploits`.",
        )
        url = CharFilter(
            label="Filter the content by a feeds URL. This is the RSS or ATOM feed used when adding the blog. Will search for URLs that contain the value entered.  Search is wildcard so `dogesec` will return any URL that contains the string `dogesec`.",
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
        profile_id = obj.get('profile_id')
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
        request_body = request.body
        s = serializers.FeedSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        resp = self.make_request(request, "/api/v1/feeds/", request_body=request_body)
        if resp.status_code == 201:
            out = json.loads(resp.content)
            out['feed_id'] = out['id']
            job = tasks.new_task(out, s.validated_data['profile_id'], s.validated_data['ai_summary_provider'])
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
            job = tasks.new_task(out, s.data.get("profile_id", feed.profile.id), s.data['ai_summary_provider'])
            return Response(JobSerializer(job).data, status=status.HTTP_201_CREATED)
        return resp

@extend_schema_view(
    list=extend_schema(
        summary="Search for Posts in a Feed",
        description=textwrap.dedent(
            """
            Use this endpoint if you want to search through all Posts in a Feed. The response of this endpoint is JSON, and is useful if you're building a custom integration to a downstream tool. If you just want to import the data for this blog into your feed reader use the RSS version of this endpoint.
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
        responses={201:JobSerializer, 404: api_schema.DEFAULT_404_ERROR},
        summary="Update a Post in A Feed",
        description=textwrap.dedent(
            """
            Occasionally updates to blog posts are not reflected in RSS and ATOM feeds. To ensure the post stored in the database matches the currently published post you make a request to this endpoint using the Post ID to update it.

            The following key/values are accepted in the body of the request:

            * `profile_id` (required - valid Profile ID): You get the last `profile_id` used for this post using the Get Jobs endpoint and post id. Changing the profile will potentially change data extracted from the blog.

            **IMPORTANT**: This action will delete the original post as well as all the STIX SDO and SRO objects created during the processing of the original text.

            The response will return the Job information responsible for getting the requested data you can track using the `id` returned via the GET Jobs by ID endpoint.
            """
        ),
    ),
    create=extend_schema(
        request=serializers.PostCreateSerializer,
        responses={201:JobSerializer, 404: api_schema.DEFAULT_404_ERROR},
        summary="Backfill a Post into A Feed",
        description=textwrap.dedent(
            """
            This endpoint allows you to add Posts manually to a Feed. This endpoint is designed to ingest posts that are not identified by the Wayback Machine (used by the POST Feed endpoint during ingestion). If the feed you want to add a post to does not already exist, you should first add it using the POST Feed endpoint.

            The following key/values are accepted in the body of the request:

            * `profile_id` (required): a valid profile ID to define how the post should be processed.

            * `link` (required - must be unique): The URL of the blog post. This is where the content of the post is found. It cannot be the same as the `url` of a post already in this feed. If you want to update the post, use the PATCH post endpoint.
            * `pubdate` (required): The date of the blog post in the format `YYYY-MM-DD`. history4feed cannot accurately determine a post date in all cases, so you must enter it manually.
            * `title` (required):  history4feed cannot accurately determine the title of a post in all cases, so you must enter it manually.
            * `author` (optional): the value to be stored for the author of the post.
            * `categories` (optional) : the value(s) to be stored for the category of the post. Pass as a list like `["tag1","tag2"]`.
            * `ai_summary_provider` (optional): you can optionally get an AI model to produce a summary of the blog. You must pass the request in format `provider:model`. Currently supported providers are:
                * `openai:`, models e.g.: `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `gpt-4` ([More here](https://platform.openai.com/docs/models))
                * `anthropic:`, models e.g.: `claude-3-5-sonnet-latest`, `claude-3-5-haiku-latest`, `claude-3-opus-latest` ([More here](https://docs.anthropic.com/en/docs/about-claude/models))
                * `gemini:models/`, models: `gemini-1.5-pro-latest`, `gemini-1.5-flash-latest` ([More here](https://ai.google.dev/gemini-api/docs/models/gemini))

            Each post ID is generated using a UUIDv5. The namespace used is `6c6e6448-04d4-42a3-9214-4f0f7d02694e` (history4feed) and the value used `<FEED_ID>+<POST_URL>+<POST_PUB_TIME (to .000000Z)>` (e.g. `d1d96b71-c687-50db-9d2b-d0092d1d163a+https://muchdogesec.github.io/fakeblog123///test3/2024/08/20/update-post.html+2024-08-20T10:00:00.000000Z` = `22173843-f008-5afa-a8fb-7fc7a4e3bfda`).

            The response will return the Job information responsible for getting the requested data you can track using the `id` returned via the GET Jobs by ID endpoint.

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
            self.remove_report(post_id, feed.collection_name)
            out = json.loads(resp.content)
            out['job_id'] = out['id']
            job = tasks.new_post_patch_task(out, s.data.get("profile_id", feed.profile.id), s.data['ai_summary_provider'])
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
            job = tasks.new_post_patch_task(out, s.data.get("profile_id", feed.profile.id), s.data['ai_summary_provider'])
            return Response(JobSerializer(job).data, status=status.HTTP_201_CREATED)
        return resp

    @extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters()
        + [
            OpenApiParameter(
                "types",
                many=True,
                explode=False,
                description="Filter the results by one or more STIX Object types",
                enum=OBJECT_TYPES,
            ),
        ],
        summary="Get STIX Objects for a specific Post",
        description=textwrap.dedent(
            """
            This endpoint will return all objects extracted for a post. If you want more flexibility to filter the objects or search for STIX objects across different Posts, use the Get Object endpoints.
            """
        ),
    )
    @decorators.action(detail=True, methods=["GET"])
    def objects(self, request, feed_id=None, post_id=None):
        return self.get_post_objects(post_id, feed_id)
    
    def get_post_objects(self, post_id, feed_id):
        helper = ArangoDBHelper(settings.VIEW_NAME, self.request)
        types = helper.query.get('types', "")
        bind_vars = {
            "@view": helper.collection,
            "matcher": dict(_obstracts_post_id=str(post_id), _obstracts_feed_id=str(feed_id)),
            "types": list(OBJECT_TYPES.intersection(types.split(","))) if types else None,
        }
        query = """
            FOR doc in @@view
            FILTER doc.type IN @types OR NOT @types
            FILTER MATCHES(doc, @matcher)

            COLLECT id = doc.id INTO docs
            LET doc = FIRST(FOR d in docs[*].doc SORT d.modified OR d.created DESC RETURN d)

            LIMIT @offset, @count
            RETURN KEEP(doc, KEYS(doc, true))
        """

        return helper.execute_query(query, bind_vars=bind_vars)

    @extend_schema(
        responses=None,
        summary="Get Markdown for specific post",
        description=textwrap.dedent(
            """
            A blog is stored in [history4feed](https://github.com/muchdogesec/history4feed/) as HTML. This HTML is then converted to markdown using [file2txt](https://github.com/muchdogesec/file2txt/) which is subsequently used to make extractions from. This endpoint will return that output.

            This endpoint is useful for debugging issues in extractions when you think there could be an issue with the content being passed to the extractors.
            """
        ),
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
        resp_text = MarkdownImageReplacer.get_markdown(request, obj.markdown_file.read().decode(), models.FileImage.objects.filter(report__post_id=post_id))
        return FileResponse(streaming_content=resp_text, content_type='text/markdown', filename='markdown.md')
    
    @extend_schema(
            responses={200: serializers.ImageSerializer(many=True), 404: api_schema.DEFAULT_404_ERROR, 400: api_schema.DEFAULT_400_ERROR},
            filters=False,
            summary="Retrieve images found in a Post",
            description=textwrap.dedent(
            """
            When [file2txt](https://github.com/muchdogesec/file2txt/) processes a file it will extract all images from the file and store them locally. You can see these images referenced in the markdown produced (see Post markdown endpoint). This endpoint lists the image files found in the Post selected.
            """
        ),
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

    def remove_report(self, post_id, collection):
        helper = ArangoDBHelper(settings.VIEW_NAME, self.request)
        query = """ 
        FOR doc IN @@collection
        FILTER doc._obstracts_post_id == @post_id
        REMOVE doc IN @@collection
        RETURN NULL
        """
        for c in ["edge_collection", "vertex_collection"]:
            helper.execute_query(query, bind_vars={"@collection": f"{collection}_{c}", 'post_id': post_id}, paginate=False)


    @extend_schema(
            responses=None,
            summary="Get a summary of the post content",
            description=textwrap.dedent(
                """
                If `ai_summary_provider` was enabled, this endpoint will return a summary of the post. This is useful to get a quick understanding of the contents of the post.

                The prompt used to generate the summary can be seen in [dogesec_commons here](https://github.com/muchdogesec/dogesec_commons/blob/main/dogesec_commons/stixifier/summarizer.py).

                If you want a summary but `ai_summary_provider` was not enabled during processing, you will need to process the post again.
                """
            ),        
    )
    @decorators.action(methods=["GET"], detail=True)
    def summary(self, request, feed_id=None, post_id=None):
        obj = get_object_or_404(models.File, post_id=post_id)
        if not obj.summary:
            raise exceptions.NotFound(f"No Summary for post")
        return FileResponse(streaming_content=io.BytesIO(obj.summary.encode()), content_type='text/markdown', filename='summary.md')


@extend_schema_view(
    list=extend_schema(
        summary="Search Jobs",
        description=textwrap.dedent(
            """
            Jobs track the status of the request to get posts for Feeds. For every new Feed added and every update to a Feed requested a job will be created. The id of a job is printed in the POST and PATCH responses respectively, but you can use this endpoint to search for the id again, if required.
            """
        ),
        responses={400: api_schema.DEFAULT_400_ERROR, 200: JobSerializer},
    ),
    retrieve=extend_schema(
        summary="Get a Job",
        description=textwrap.dedent(
            """
            Using a Job ID you can retrieve information about its state via this endpoint. This is useful to see if a Job to get data is complete, how many posts were imported in the job, or if an error has occurred.
            """
        ),
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
            label="Filter by Feed ID (e.g. `6c6e6448-04d4-42a3-9214-4f0f7d02694e`.",
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
    
@extend_schema_view(
    list=extend_schema(
        summary="Search for Jobs run for this Feed",
        description=textwrap.dedent(
            """
            Jobs track the status of the request to get posts for Feeds. For every new Feed added and every update to a Feed requested a job will be created. The id of a job is printed in the POST and PATCH responses respectively, but you can use this endpoint to search for the id again, if required.
            """
        ),
        responses={400: api_schema.DEFAULT_400_ERROR, 200: JobSerializer},
    ),
    retrieve=extend_schema(
        summary="Get a Job run for this Feed",
        description=textwrap.dedent(
            """
            Using a Job ID you can retrieve information about its state via this endpoint. This is useful to see if a Job to get data is complete, how many posts were imported in the job, or if an error has occurred.
            """
        ),
        responses={404: api_schema.DEFAULT_404_ERROR, 200: JobSerializer},
    ),
)
class FeedJobView(JobView):
    openapi_tags = ["Feeds"]

    class filterset_class(JobView.filterset_class):
        feed_id = None

    def get_queryset(self):
        return models.Job.objects.filter(feed_id=self.kwargs.get('feed_id'))


def make_h4f_request(path, method="GET", params=None, body=None, headers={}):
    url = urljoin(settings.HISTORY4FEED_URL, path)
    headers["host"] = "localhost"
    return requests.request(method, url, params=params, headers=headers, data=body)
