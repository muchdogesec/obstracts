import io
import json
import logging
from urllib.parse import urljoin
from django.http import Http404, HttpResponse, FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, decorators, exceptions, status, renderers
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, PolymorphicProxySerializer
from drf_spectacular.types import OpenApiTypes
from .import autoschema as api_schema
from dogesec_commons.objects.helpers import OBJECT_TYPES
import hyperlink
from django.db.models import OuterRef, Subquery
from dogesec_commons.objects.helpers import ArangoDBHelper
from .utils import (
    MinMaxDateFilter,
    Ordering,
    Pagination,
    Response,
)
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, Filter, BaseCSVFilter, UUIDFilter, CharFilter, MultipleChoiceFilter, filters
from .serializers import (
    JobSerializer,
    FeedSerializer,
)
from . import h4fserializers
import txt2stix.txt2stix
import requests
from django.conf import settings
from drf_spectacular.utils import extend_schema, extend_schema_view
from history4feed.app import views as h4f_views
from . import models
from .autoschema import ObstractsAutoSchema
from dogesec_commons.utils import custom_exception_handler

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
        responses={200: h4fserializers.FeedXSerializer, 400: api_schema.DEFAULT_400_ERROR}
    ),
    retrieve=extend_schema(
        summary="Get a Feed",
        description=textwrap.dedent(
            """
            Use this endpoint to get information about a specific feed using its ID. You can search for a Feed ID using the GET Feeds endpoint, if required.
            """
        ),
        responses={200: h4fserializers.FeedXSerializer, 404: api_schema.DEFAULT_404_ERROR, 400: api_schema.DEFAULT_400_ERROR}
    ),
    create=extend_schema(
        request=FeedSerializer,
        responses={201:JobSerializer, 400: api_schema.DEFAULT_400_ERROR},
        summary="Create a New Feed",
        description=textwrap.dedent(
            """
            Use this endpoint to create to a new Feed.

            The following key/values are accepted in the body of the request:

            * `url` (required): should be a valid RSS or ATOM feed URL. If it is not valid, the Feed will not be created and an error returned. If the `url` is already associated with an existing Feed, a request to this endpoint will trigger an update request for the blog (you can also use the PATCH Feed endpoint to achieve the same thing). If you want to add the `url` with new settings, first delete the Feed it is associated with.
            * `profile_id` (required - valid Profile ID): You can view existing Profiles, or generated a new one using the Profiles endpoints. You can update the `profile` used for future posts in a Feed, or reindex Posts using a different `profile_id` later. See the Patch Feed and Patch Post endpoints for more information.
            * `include_remote_blogs` (required): is a boolean setting and will ask history4feed to ignore any feeds not on the same domain as the URL of the feed. Some feeds include remote posts from other sites (e.g. for a paid promotion). This setting (set to `false` allows you to ignore remote posts that do not use the same domain as the `url` used). Generally you should set `include_remote_blogs` to false. The one exception is when things like feed aggregators (e.g. Feedburner) URLs are used, where the actual blog posts are not on the `feedburner.com` (or whatever) domain. In this case `include_remote_blogs` should be set to `true`.
            * `pretty_url` (optional): you can also include a secondary URL in the database. This is designed to be used to show the link to the blog (not the RSS/ATOM) feed so that a user can navigate to the blog in their browser.
            * `title` (optional): the title of the feed will be used if not passed. You can also manually pass the title of the blog here.
            * `description` (optional): the description of the feed will be used if not passed. You can also manually pass the description of the blog here.

            The `id` of a Feed is generated using a UUIDv5. The namespace used is `6c6e6448-04d4-42a3-9214-4f0f7d02694e` (history4feed) and the value used is `<FEED_URL>` (e.g. `https://muchdogesec.github.io/fakeblog123/feeds/rss-feed-encoded.xml` would have the id `d1d96b71-c687-50db-9d2b-d0092d1d163a`). Therefore, you cannot add a URL that already exists, you must first delete it to add it with new settings.

            Each post ID is generated using a UUIDv5. The namespace used is `6c6e6448-04d4-42a3-9214-4f0f7d02694e` (history4feed) and the value used `<FEED_ID>+<POST_URL>+<POST_PUB_TIME (to .000000Z)>` (e.g. `d1d96b71-c687-50db-9d2b-d0092d1d163a+https://muchdogesec.github.io/fakeblog123///test3/2024/08/20/update-post.html+2024-08-20T10:00:00.000000Z` = `22173843-f008-5afa-a8fb-7fc7a4e3bfda`).

            The response will return the Job information responsible for getting the requested data you can track using the `id` returned via the GET Jobs by ID endpoint.
            """
        ),
    ),
    create_skeleton=extend_schema(
        request=serializers.SkeletonFeedSerializer,
        responses={201:FeedSerializer, 400: api_schema.DEFAULT_400_ERROR},
        summary="Create a New Skeleton Feed",
        description=textwrap.dedent(
            """
            Sometimes blogs don't have an RSS or ATOM feed. It might also be the case you want to curate a blog manually using various URLs. This is what `skeleton` feeds are designed for, allowing you to create a skeleton feed and then add posts to it manually later on using the add post manually endpoint.

            The following key/values are accepted in the body of the request:

            * `url` (required): the URL to be attached to the feed. Needs to be a URL (because this is what feed ID is generated from), however does not need to be valid.
            * `pretty_url` (optional): you can also include a secondary URL in the database. This is designed to be used to show the link to the blog (not the RSS/ATOM) feed so that a user can navigate to the blog in their browser.
            * `title` (required): the title of the feed
            * `description` (optional): the description of the feed

            The response will return the created Feed object with the Feed `id`.
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
        responses={201: serializers.FeedSerializer, 404: api_schema.DEFAULT_404_ERROR, 400: api_schema.DEFAULT_400_ERROR},
        summary="Update a Feeds Metadata",
        description=textwrap.dedent(
            """
            Update the metadata of the Feed.

            Note, it is not possible to update the `url` of the feed. You must delete the Feed and add it again to modify the `url`.

            The following key/values are accepted in the body of the request:

            * `title` (optional): update the `title` of the Feed
            * `description` (optional): update the `description` of the Feed
            * `pretty_url` (optional): update the `pretty_url of the Feed

            Only one/key value is required in the request. For those not passed, the current value will remain unchanged.

            The response will contain the newly updated Feed object.
            """
        ),
    ),
    fetch=extend_schema(
        request=serializers.FetchFeedSerializer,
        responses={201: serializers.JobSerializer, 404: api_schema.DEFAULT_404_ERROR, 400: api_schema.DEFAULT_400_ERROR},
        summary="Fetch Updates for a Feed",
        description=textwrap.dedent(
            """
            Use this endpoint to check for new posts on this blog since the last post time. An update request will immediately trigger a job to get the posts between `latest_item_pubdate` for feed and time you make a request to this endpoint.

            Note, this endpoint can miss updates that have happened to currently indexed posts (where the RSS or ATOM feed does not report the updated date correctly -- which is actually very common). To solve this issue for currently indexed blog posts, use the Update a Post in a Feed endpoint directly.

            Whilst it is possible to modify the `profile_id` and `include_remote_blogs` options when updating a Feed we would recommend using the same `profile_id` and `include_remote_blogs` as set originally because. it can becoming confusing quickly managing different settings on a per post basis. Generally it's better to reindex the whole blog using the new setting unless you have a good reason not to.

            The following key/values are accepted in the body of the request:

            * `profile_id` (required - valid Profile ID): You get the last `profile_id` used for this feed using the Get Jobs endpoint and feed id. Changing this setting will only apply to posts after the `latest_item_pubdate`.
            * `include_remote_blogs` (required): You get the last `include_remote_blogs` used for this feed using the Get Jobs endpoint and feed id. Changing this setting will only apply to posts after the `latest_item_pubdate`.

            Each post ID is generated using a UUIDv5. The namespace used is `6c6e6448-04d4-42a3-9214-4f0f7d02694e` (history4feed) and the value used `<FEED_ID>+<POST_URL>+<POST_PUB_TIME (to .000000Z)>` (e.g. `d1d96b71-c687-50db-9d2b-d0092d1d163a+https://muchdogesec.github.io/fakeblog123///test3/2024/08/20/update-post.html+2024-08-20T10:00:00.000000Z` = `22173843-f008-5afa-a8fb-7fc7a4e3bfda`).

            IMPORTANT: this request will fail if run against a Skeleton type feed. Skeleton feeds can only be updated by adding posts to them manually using the Manually Add a Post to a Feed endpoint.

            The response will return the Job information responsible for getting the requested data you can track using the `id` returned via the GET Jobs by ID endpoint.
            """
        ),
    ),
)
class FeedView(h4f_views.FeedView):
    lookup_url_kwarg = "feed_id"
    openapi_tags = ["Feeds"]
    serializer_class = serializers.FeedSerializer
    pagination_class = Pagination("feeds")
    schema = ObstractsAutoSchema()

    def create(self, request, *args, **kwargs):
        request_body = request.body
        s = serializers.FeedSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        h4f_job = self.new_create_job(request)
        job = tasks.new_task(h4f_job, s.validated_data['profile_id'])
        return Response(JobSerializer(job).data, status=status.HTTP_201_CREATED)
    
    @decorators.action(methods=["PATCH"], detail=True)
    def fetch(self, request, *args, **kwargs):
        s = serializers.FetchFeedSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        h4f_job = self.new_fetch_job(request)
        job = tasks.new_task(h4f_job, s.validated_data['profile_id'])
        return Response(JobSerializer(job).data, status=status.HTTP_201_CREATED)


    
@extend_schema_view(
    list=extend_schema(
        summary="Search for Posts",
        description=textwrap.dedent(
            """
            Search through Posts from all Blogs. Filter by the ones you're interested in.
            """
        ),
        responses={200:serializers.PostWithFeedIDSerializer, 400: api_schema.DEFAULT_400_ERROR},
    ),
    retrieve=extend_schema(
        summary="Get a Post",
        description=textwrap.dedent(
            """
            This will return a single Post by its ID. It is useful if you only want to get the data for a single entry.
            """
        ),
    ),
    destroy=extend_schema(
        summary="Delete a post in a Feed",
        description=textwrap.dedent(
            """
            Use this endpoint to delete a post using its `id`

            IMPORTANT: this WILL delete the content of the post and any STIX objects directly linked to it. Any objects linked to other reports WILL NOT be deleted.
            """
        ),
        responses={204: {}, 404: api_schema.DEFAULT_404_ERROR}
    ),
    reindex=extend_schema(
        request=serializers.FetchPostSerializer,

        responses={201:JobSerializer, 404: api_schema.DEFAULT_404_ERROR, 400: api_schema.DEFAULT_400_ERROR},
        summary="Update a Post in a Feed",
        description=textwrap.dedent(
            """

            Occasionally updates to blog posts are not reflected in RSS and ATOM feeds. To ensure the post stored in the database matches the currently published post you make a request to this endpoint using the Post ID to update it.

            The following key/values are accepted in the body of the request:

            * `profile_id` (required - valid Profile ID): You get the last `profile_id` used for this post using the Get Jobs endpoint and post id. Changing the profile will potentially change data extracted from the blog.

            This update change the content (`description`) stored for the Post and rerun the extractions on the new content for the Post.

            It will not update the `title`, `pubdate`, `author`, or `categories`. If you need to update these properties you can use the Update Post Metadata endpoint.

            **IMPORTANT**: This action will delete the original post as well as all the STIX SDO and SRO objects created during the processing of the original text. Mostly this is not an issue, however, if the post has been removed at source you will end up with an empty entry for this Post.

            The response will return the Job information responsible for getting the requested data you can track using the `id` returned via the GET Jobs by ID endpoint.
            """
        ),
    ),
    partial_update=extend_schema(
        summary="Update a Posts Metadata",
        description=textwrap.dedent(
            """
            In most cases, the automatically indexed metadata (or user submitted metadata in the case of manually added Posts) will be fine.

            However, these may be occasions you want to change the values of the `title`, `pubdate`, `author`, or `categories` for a Post.

            The following key/values are accepted in the body of the request:

            * `pubdate` (required): The date of the blog post in the format `YYYY-MM-DD`. history4feed cannot accurately determine a post date in all cases, so you must enter it manually.
            * `title` (required):  history4feed cannot accurately determine the title of a post in all cases, so you must enter it manually.
            * `author` (optional): the value to be stored for the author of the post.
            * `categories` (optional) : the value(s) to be stored for the category of the post. Pass as a list like `["tag1","tag2"]`.

            Only one key/value is required. If no values are passed, they will be remain unchanged from the current state.

            It is not possible to manually modify any other values for the Post object. You can update the post content using the Update a Post in A Feed endpoint.
            """
        ),

        responses={
            201: serializers.PostWithFeedIDSerializer,
            404: api_schema.DEFAULT_404_ERROR,
            400: api_schema.DEFAULT_400_ERROR,
        },
        request=serializers.PatchPostSerializer,
    ),
)
class PostOnlyView(h4f_views.PostOnlyView):
    serializer_class = serializers.PostWithFeedIDSerializer
    file_serializer_class = serializers.FileSerializer
    lookup_url_kwarg = 'post_id'
    openapi_tags = ["Posts"]
    schema = ObstractsAutoSchema()

    pagination_class = Pagination("posts")
    filter_backends = [DjangoFilterBackend, Ordering, MinMaxDateFilter]

    class filterset_class(h4f_views.PostOnlyView.filterset_class):
        job_state = filters.ChoiceFilter(choices=models.JobState.choices, help_text="Filter by obstracts job status")

    def get_queryset(self):
        return super().get_queryset() \
            .annotate(job_state=Subquery(models.Job.objects.filter(history4feed_job_id=OuterRef('last_job_id')).values('state')[:1]))


    @decorators.action(detail=True, methods=['PATCH'], serializer_class=serializers.CreateTaskSerializer)
    def reindex(self, request, *args, **kwargs):
        s = serializers.FetchFeedSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        _, h4f_job = self.new_reindex_post_job(request)
        job = tasks.new_post_patch_task(h4f_job, s.validated_data["profile_id"])
        return Response(JobSerializer(job).data, status=status.HTTP_201_CREATED)
    
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

            You can find these objects in the database using the filter `_stix2arango_note` and value `stixify-job--<POST ID>`.
            """
        ),
    )
    @decorators.action(detail=True, methods=["GET"])
    def objects(self, request, post_id=None, **kwargs):
        return self.get_post_objects(post_id)
    
    def get_post_objects(self, post_id):
        post_file = get_object_or_404(models.File, post_id=post_id)

        helper = ArangoDBHelper(settings.ARANGODB_DATABASE_VIEW, self.request)
        types = helper.query.get('types', "")
        bind_vars = {
            "types": list(OBJECT_TYPES.intersection(types.split(","))) if types else None,
            "@vertex_collection":post_file.feed.vertex_collection,
            "@edge_collection": post_file.feed.edge_collection,
            "report_id": post_file.report_id,
        }
        query = """

LET report = FIRST(
    FOR report IN @@vertex_collection
    FILTER report.id == @report_id
    RETURN report
)

LET original_objects = APPEND([report], (
    FOR doc IN @@vertex_collection
    FILTER doc.id IN report.object_refs
    RETURN doc
))


LET relationship_objects = (
    FOR doc IN @@edge_collection
    FILTER doc.source_ref IN original_objects[*].id OR doc.target_ref IN original_objects[*].id
    RETURN doc
)

LET report_ref_vertices = (
    FOR doc IN @@vertex_collection
    FILTER doc.id IN APPEND(report.object_marking_refs, [report.created_by_ref])
    RETURN doc
)

FOR doc IN UNION_DISTINCT(report_ref_vertices, original_objects, relationship_objects)
    FILTER NOT @types OR doc.type IN @types
    
    COLLECT id = doc.id  INTO docs
    LET dd = FIRST(FOR doc IN docs[*].doc RETURN doc)
    
    LIMIT @offset, @count
    RETURN KEEP(dd, KEYS(dd, TRUE))

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
    def markdown(self, request, post_id=None, **kwargs):
        obj = get_object_or_404(models.File, post_id=post_id)
        resp_text = MarkdownImageReplacer.get_markdown(request, obj.markdown_file.read().decode(), models.FileImage.objects.filter(report__post_id=post_id))
        return FileResponse(streaming_content=resp_text, content_type='text/markdown', filename='markdown.md')
    
    @extend_schema(
            responses={200: serializers.ImageSerializer(many=True), 404: api_schema.DEFAULT_404_ERROR, 400: api_schema.DEFAULT_400_ERROR},
            filters=False,
            summary="Get Local URLs for Images in a Post",
            description=textwrap.dedent(
            """
            When [file2txt](https://github.com/muchdogesec/file2txt/) processes a file it will extract all images from the file and store them locally. You can see these images referenced in the markdown produced (see Post markdown endpoint). This endpoint lists the image files found in the Post selected.
            """
        ),
    )
    @decorators.action(detail=True, pagination_class=Pagination("images"))
    def images(self, request, post_id=None, image=None, **kwargs):
        queryset = models.FileImage.objects.filter(report__post_id=post_id).order_by('name')
        paginator = Pagination('images')

        page = paginator.paginate_queryset(queryset, request, self)

        if page is not None:
            serializer = serializers.ImageSerializer(page, many=True, context=dict(request=request))
            return paginator.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def remove_report(self, post_id):
        try:
            post: models.File = get_object_or_404(models.File, post_id=post_id)
            collection = post.feed.collection_name

            helper = ArangoDBHelper(settings.ARANGODB_DATABASE_VIEW, self.request)
            query = """ 
            FOR doc IN @@collection
            FILTER doc._obstracts_post_id == @post_id
            REMOVE doc IN @@collection
            RETURN NULL
            """
            for c in ["edge_collection", "vertex_collection"]:
                helper.execute_query(query, bind_vars={"@collection": f"{collection}_{c}", 'post_id': post_id}, paginate=False)
        except Exception as e:
            logging.exception("remove_report failed")

@extend_schema_view(
    create=extend_schema(
        request=serializers.PostCreateSerializer,
        responses={201:JobSerializer, 404: api_schema.DEFAULT_404_ERROR, 400: api_schema.DEFAULT_400_ERROR},
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

            Each post ID is generated using a UUIDv5. The namespace used is `6c6e6448-04d4-42a3-9214-4f0f7d02694e` (history4feed) and the value used `<FEED_ID>+<POST_URL>+<POST_PUB_TIME (to .000000Z)>` (e.g. `d1d96b71-c687-50db-9d2b-d0092d1d163a+https://muchdogesec.github.io/fakeblog123///test3/2024/08/20/update-post.html+2024-08-20T10:00:00.000000Z` = `22173843-f008-5afa-a8fb-7fc7a4e3bfda`).

            The response will return the Job information responsible for getting the requested data you can track using the `id` returned via the GET Jobs by ID endpoint.

            _Note: We do have a proof-of-concept to scrape a site for all blog post urls, titles, and pubdate called [sitemap2posts](https://github.com/muchdogesec/sitemap2posts) which can help form the request body needed for this endpoint._
            """
        ),
    ),
)
class FeedPostView(h4f_views.feed_post_view, PostOnlyView):
    schema = ObstractsAutoSchema()

    openapi_tags = [ "Feeds" ]

    class filterset_class(h4f_views.FeedPostView.filterset_class):
        job_state = filters.ChoiceFilter(choices=models.JobState.choices, help_text="Filter by obstracts job status")
        
    @property
    def h4f_base_path(self):
        return f"/api/v1/feeds/{self.kwargs['feed_id']}/posts"
    


    def create(self, request, *args, **kwargs):
        s = serializers.FetchFeedSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        h4f_job = self.new_create_post_job(request, self.kwargs['feed_id'])
        job = tasks.new_post_patch_task(h4f_job, s.validated_data["profile_id"])
        return Response(JobSerializer(job).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Update all Posts in a feed",
        description=textwrap.dedent(
            """
                This endpoint will reindex the Post content (`description`) for all Post IDs currently listed in the Feed.

                The following key/values are accepted in the body of the request:

                * profile_id (required - valid Profile ID): You get the last `profile_id` used for this feed using the Get Jobs endpoint and post ID. Changing the profile will potentially change data extracted from each post on reindex.

                This update change the content (`description`) stored for the Post and rerun the extractions on the new content for the Post.

                It will not update the `title`, `pubdate`, `author`, or `categories`. If you need to update these properties you can use the Update Post Metadata endpoint.

                **IMPORTANT**: This action will delete the original post as well as all the STIX SDO and SRO objects created during the processing of the original text. Mostly this is not an issue, however, if the post has been removed at source you will end up with an empty entry for this Post.

                Note, if you only want to update the content of a single post, it is much more effecient to use the Update a Post in a Feed endpoint.

                The response will return the Job information responsible for getting the requested data you can track using the id returned via the GET Jobs by ID endpoint.
            """
        ),
        responses={201:JobSerializer, 404: api_schema.DEFAULT_404_ERROR, 400: api_schema.DEFAULT_400_ERROR},
        request=serializers.CreateTaskSerializer,
    )
    @decorators.action(methods=["PATCH"], detail=False, url_path='reindex')
    def reindex_feed(self, request, *args, feed_id=None, **kwargs):
        s = serializers.CreateTaskSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        h4f_job = self.new_reindex_feed_job(feed_id)
        job = tasks.new_post_patch_task(h4f_job, s.validated_data["profile_id"])
        return Response(JobSerializer(job).data, status=status.HTTP_201_CREATED)

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
    schema = ObstractsAutoSchema()
    http_method_names = ["get"]
    serializer_class = JobSerializer
    openapi_tags = ["Jobs"]
    lookup_url_kwarg = "job_id"
    filter_backends = [DjangoFilterBackend, Ordering]
    ordering_fields = ["created", "item_count"]
    ordering = "created_descending"
    pagination_class = Pagination("jobs")


    class filterset_class(FilterSet):
        feed_id = BaseCSVFilter(
            label="Filter by Feed ID (e.g. `6c6e6448-04d4-42a3-9214-4f0f7d02694e`.",
            lookup_expr='in'
        )
        state = Filter(
            label="Filter by state.",
        )
        post_id = UUIDFilter(label="Filter by Post ID", field_name="history4feed_job__fulltext_jobs__post_id")


    def get_queryset(self):
        return models.Job.objects

