from functools import reduce
import operator
from django.http import FileResponse
from django.urls import resolve
from rest_framework import viewsets, decorators, exceptions, status, renderers, mixins
from drf_spectacular.utils import (
    OpenApiParameter,
)
from drf_spectacular.types import OpenApiTypes
from stix2arango.services import ArangoDBService

from obstracts.server.md_helper import MarkdownImageReplacer
from . import autoschema as api_schema
from dogesec_commons.objects.helpers import OBJECT_TYPES
from django.db.models import OuterRef, Subquery, Q
from dogesec_commons.objects.helpers import ArangoDBHelper
from .utils import (
    FEED_406_ERROR,
    MinMaxDateFilter,
    Ordering,
    Pagination,
    Response,
)
from django_filters.rest_framework import (
    DjangoFilterBackend,
    FilterSet,
    Filter,
    BaseCSVFilter,
    UUIDFilter,
    filters,
)
from .serializers import (
    ObstractsJobSerializer,
    FeedCreateSerializer,
)
from .serializers import h4fserializers
from django.conf import settings
from drf_spectacular.utils import extend_schema, extend_schema_view
from history4feed.app import views as h4f_views
from . import models
from .autoschema import ObstractsAutoSchema

from ..cjob import tasks
from obstracts.server import serializers
import textwrap

ATTACK_DOMAINS = ["ics", "mobile", "enterprise"]

from drf_spectacular.views import SpectacularAPIView
from rest_framework.response import Response


class SchemaViewCached(SpectacularAPIView):
    _schema = None

    def _get_schema_response(self, request):
        version = (
            self.api_version or request.version or self._get_version_parameter(request)
        )
        if not self.__class__._schema:
            generator = self.generator_class(
                urlconf=self.urlconf, api_version=version, patterns=self.patterns
            )
            self.__class__._schema = generator.get_schema(
                request=request, public=self.serve_public
            )
        return Response(
            data=self.__class__._schema,
            headers={
                "Content-Disposition": f'inline; filename="{self._get_filename(request, version)}"'
            },
        )


class PlainMarkdownRenderer(renderers.BaseRenderer):
    media_type = "text/markdown"
    format = "text/markdown"


@extend_schema_view(
    list=extend_schema(
        summary="Search for Feeds",
        description=textwrap.dedent(
            """
            Use this endpoint to get a list of all the feeds you are currently subscribed to. This endpoint is usually used to get the id of feed you want to get blog post data for in a follow up request to the GET Feed Posts endpoints or to get the status of a job related to the Feed in a follow up request to the GET Job endpoint. If you already know the id of the Feed already, you can use the GET Feeds by ID endpoint.
            """
        ),
        responses={
            200: h4fserializers.FeedSerializer,
            400: api_schema.DEFAULT_400_ERROR,
        },
    ),
    retrieve=extend_schema(
        summary="Get a Feed",
        description=textwrap.dedent(
            """
            Use this endpoint to get information about a specific feed using its ID. You can search for a Feed ID using the GET Feeds endpoint, if required.
            """
        ),
        responses={
            200: h4fserializers.FeedSerializer,
            404: api_schema.DEFAULT_404_ERROR,
            400: api_schema.DEFAULT_400_ERROR,
        },
    ),
    create=extend_schema(
        request=FeedCreateSerializer,
        responses={201: ObstractsJobSerializer, 400: api_schema.DEFAULT_400_ERROR, 406: FEED_406_ERROR},
        summary="Create a New Feed",
        description=textwrap.dedent(
            """
            Use this endpoint to create to a new Feed.

            The following key/values are accepted in the body of the request:

            * `profile_id` (required - valid Profile ID): You can view existing Profiles, or generated a new one using the Profiles endpoints. You can update the `profile` used for future posts in a Feed, or reindex Posts using a different `profile_id` later. See the Patch Feed and Patch Post endpoints for more information.
            * `url` (required): a valid RSS or ATOM feed URL (if `use_search_index` = `false`) OR the URL of the blog (if `use_search_index` = `true`).
            * `include_remote_blogs` (required): is a boolean setting and will ask history4feed to ignore any feeds not on the same domain as the URL of the feed. Some RSS/ATOM feeds include remote posts from other sites (e.g. for a paid promotion). This setting (set to `false` allows you to ignore remote posts that do not use the same domain as the `url` used). Generally you should set `include_remote_blogs` to `false`. The one exception is when things like feed aggregators (e.g. Feedburner) URLs are used, where the actual blog posts are not on the `feedburner.com` (or whatever) domain. In this case `include_remote_blogs` should be set to `true`.
            * `pretty_url` (optional): you can also include a secondary URL in the database. This is designed to be used to show the link to the blog (not the RSS/ATOM) feed so that a user can navigate to the blog in their browser.
            * `title` (optional): the title of the feed will be used if not passed. You can also manually pass the title of the blog here.
            * `description` (optional): the description of the feed will be used if not passed. You can also manually pass the description of the blog here.
            * `use_search_index` (optional, default is `false`): If the `url` is not a valid RSS or ATOM feed you must set this mode to `true`. Set to `true` this mode uses search results that contain the base `url` passed vs. the RSS/ATOM feed entries (when this mode is set to `false`). This mode is only be able to index results in Google Search, so can miss some sites entirely where they are not indexed by Google. You must also pass a `title` and `description` when setting this mode to `true`. Note, you can use the skeleton endpoint to create a feed manually from a non RSS/ATOM URL or where search results do not satisfy your use case.

            The `id` of a Feed is generated using a UUIDv5. The namespace used is `6c6e6448-04d4-42a3-9214-4f0f7d02694e` (history4feed) and the value used is `<FEED_URL>` (e.g. `https://muchdogesec.github.io/fakeblog123/feeds/rss-feed-encoded.xml` would have the id `d1d96b71-c687-50db-9d2b-d0092d1d163a`). Therefore, you cannot add a URL that already exists, you must first delete it to add it with new settings.

            Each post ID is generated using a UUIDv5. The namespace used is `6c6e6448-04d4-42a3-9214-4f0f7d02694e` (history4feed) and the value used `<FEED_ID>+<POST_URL>+<POST_PUB_TIME (to .000000Z)>` (e.g. `d1d96b71-c687-50db-9d2b-d0092d1d163a+https://muchdogesec.github.io/fakeblog123///test3/2024/08/20/update-post.html+2024-08-20T10:00:00.000000Z` = `22173843-f008-5afa-a8fb-7fc7a4e3bfda`).

            The response will return the Job information responsible for getting the requested data you can track using the `id` returned via the GET Jobs by ID endpoint.
            """
        ),
    ),
    create_skeleton=extend_schema(
        request=serializers.SkeletonFeedSerializer,
        responses={201: FeedCreateSerializer, 400: api_schema.DEFAULT_400_ERROR},
        summary="Create a New Skeleton Feed",
        description=textwrap.dedent(
            """
            Sometimes it might be the case you want to curate a blog manually using various URLs from different blogs. This is what `skeleton` feeds are designed for, allowing you to create a skeleton feed and then add posts to it manually later on using the add post manually endpoint.

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
            Use this endpoint to delete a Feed using its ID.

            This will delete all posts (items) that belong to the feed in the database and all STIX objects created for extractions belonging to this feed (this also includes the STIX Identity object representing this Feed).

            BEWARE: this action cannot be reversed.
            """
        ),
        responses={204: {}, 404: api_schema.DEFAULT_404_ERROR},
    ),
    partial_update=extend_schema(
        responses={
            201: serializers.FeedCreateSerializer,
            404: api_schema.DEFAULT_404_ERROR,
            400: api_schema.DEFAULT_400_ERROR,
        },
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
        responses={
            201: serializers.ObstractsJobSerializer,
            404: api_schema.DEFAULT_404_ERROR,
            400: api_schema.DEFAULT_400_ERROR,
        },
        summary="Fetch Updates for a Feed",
        description=textwrap.dedent(
            """
            Use this endpoint to check for new posts on this blog since the last post time. An update request will immediately trigger a job to get the posts between `latest_item_pubdate` for feed and time you make a request to this endpoint.

            Whilst it is possible to modify the `profile_id` and `include_remote_blogs` options when updating a Feed we would recommend using the same `profile_id` and `include_remote_blogs` as set originally because it can quickly become confusing managing different settings on a per post basis. Generally it's better to reindex the whole blog using the new setting unless you have a good reason not to.

            The following key/values are accepted in the body of the request:

            * `profile_id` (required - valid Profile ID): You get the last `profile_id` used for this feed using the Get Jobs endpoint and feed id. Changing this setting will only apply to posts after the `latest_item_pubdate`.
            * `include_remote_blogs` (required): You get the last `include_remote_blogs` used for this feed using the Get Jobs endpoint and feed id. Changing this setting will only apply to posts after the `latest_item_pubdate`.

            Each post ID is generated using a UUIDv5. The namespace used is `6c6e6448-04d4-42a3-9214-4f0f7d02694e` (history4feed) and the value used `<FEED_ID>+<POST_URL>+<POST_PUB_TIME (to .000000Z)>` (e.g. `d1d96b71-c687-50db-9d2b-d0092d1d163a+https://muchdogesec.github.io/fakeblog123///test3/2024/08/20/update-post.html+2024-08-20T10:00:00.000000Z` = `22173843-f008-5afa-a8fb-7fc7a4e3bfda`).

            **IMPORTANT:** this request will fail if run against a Skeleton type feed. Skeleton feeds can only be updated by adding posts to them manually using the Manually Add a Post to a Feed endpoint.

            **IMPORTANT:** this endpoint can miss updates that have happened to currently indexed posts (where the RSS or ATOM feed or search results do not report the updated date correctly -- which is actually very common). To solve this issue for currently indexed blog posts, use the Update a Post in a Feed endpoint directly.

            The response will return the Job information responsible for getting the requested data you can track using the `id` returned via the GET Jobs by ID endpoint.
            """
        ),
    ),
)
class FeedView(h4f_views.FeedView):
    lookup_url_kwarg = "feed_id"
    openapi_tags = ["Feeds"]
    serializer_class = serializers.FeedCreateSerializer
    pagination_class = Pagination("feeds")
    schema = ObstractsAutoSchema()

    def create(self, request, *args, **kwargs):
        request_body = request.body
        s = serializers.FeedCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        h4f_job = self.new_create_job(request)
        job = tasks.new_task(h4f_job, s.validated_data["profile_id"])
        return Response(
            ObstractsJobSerializer(job).data, status=status.HTTP_201_CREATED
        )

    @decorators.action(methods=["PATCH"], detail=True)
    def fetch(self, request, *args, **kwargs):
        s = serializers.FetchFeedSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        h4f_job = self.new_fetch_job(request)
        job = tasks.new_task(h4f_job, s.validated_data["profile_id"])
        return Response(
            ObstractsJobSerializer(job).data, status=status.HTTP_201_CREATED
        )


@extend_schema_view(
    list=extend_schema(
        summary="Search for Posts",
        description=textwrap.dedent(
            """
            Search through Posts from all Blogs. Filter by the ones you're interested in.
            """
        ),
        responses={
            200: serializers.PostWithFeedIDSerializer,
            400: api_schema.DEFAULT_400_ERROR,
        },
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
        responses={204: {}, 404: api_schema.DEFAULT_404_ERROR},
    ),
    reindex=extend_schema(
        request=serializers.FetchPostSerializer,
        responses={
            201: ObstractsJobSerializer,
            404: api_schema.DEFAULT_404_ERROR,
            400: api_schema.DEFAULT_400_ERROR,
        },
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
    list_attack_navigators=extend_schema(
        summary="Show available ATT&CK Navigator Domains",
        description=textwrap.dedent(
            """
            This endpoint will return available ATT&CK Navigator layers for this post.

            An ATT&CK Navigator layer will only be generated if `ai_create_attack_navigator_layer` is set to true, and you enable ATT&CK Enterprise/ICS/Mobile extractions (which extract data).
            """
        ),
    ),
    retrieve_attack_navigators=extend_schema(
        summary="Retrieve the ATT&CK Navigator layer",
        description=textwrap.dedent(
            """
            This endpoint will return the ATT&CK Navigator layer for the specified domain. The layer file produced can be imported directly to the ATT&CK Navigator.

            Note, if no ATT&CK Navigator layer exists for the specified domain, for the post, a 404 will be returned. You can check if a layer exists using the show available layers endpoint.
            """
        ),
        parameters=[OpenApiParameter("attack_domain", enum=ATTACK_DOMAINS, location=OpenApiParameter.PATH)],
    ),
)
class PostOnlyView(h4f_views.PostOnlyView):
    serializer_class = serializers.PostWithFeedIDSerializer
    lookup_url_kwarg = "post_id"
    lookup_field = "id"
    openapi_tags = ["Posts (by ID)"]
    schema = ObstractsAutoSchema()

    pagination_class = Pagination("posts")
    filter_backends = [DjangoFilterBackend, Ordering, MinMaxDateFilter]
    ordering = "pubdate_descending"

    class filterset_class(h4f_views.PostOnlyView.filterset_class):
        incident_classification_types = [
            "other",
            "apt_group",
            "vulnerability",
            "data_leak",
            "malware",
            "ransomware",
            "infostealer",
            "threat_actor",
            "campaign",
            "exploit",
            "cyber_crime",
            "indicator_of_compromise",
            "ttp",
        ]
        show_hidden_posts = filters.BooleanFilter(
            method="show_hidden_posts_filter",
            help_text="Show only posts that have been processed (where `visible` property is `true`. This is different to `job_state` which considers state of entire job, whereas this considers state of post within job.",
            initial=False,
        )
        job_state = filters.ChoiceFilter(
            choices=models.JobState.choices,
            help_text="Filter by Obstracts job status. Use `show_hidden_posts` filter to apply at post level.",
        )
        ai_describes_incident = filters.ChoiceFilter(
            method="ai_describes_incident_filter",
            choices=[("true", "True"), ("false", "False"), ("null", "Unset")],
            help_text="If `ai_content_check_provider` set in Profile, the post will be analysed to see if it describes an incident. You can filter the results to only include post that the AI believes describes a security incident.",
        )
        ai_incident_classification = filters.MultipleChoiceFilter(
            help_text="If `ai_content_check_provider` set in Profile and the AI believes the post describes a security incident, then it will also try an assign a classification of the incident. You can filter the results to only include the desired classification.",
            method="ai_incident_classification_filter",
            choices=[(c, c) for c in incident_classification_types],
        )

        def ai_describes_incident_filter(self, queryset, name, value):
            fv = None
            match value:
                case "true":
                    fv = True
                case "false":
                    fv = False
                case _:
                    fv = None
            return queryset.filter(obstracts_post__ai_describes_incident=fv)

        def ai_incident_classification_filter(self, queryset, name, value):
            filter = reduce(
                operator.or_,
                [
                    Q(obstracts_post__ai_incident_classification__icontains=s)
                    for s in value
                ],
            )
            return queryset.filter(filter)

        def show_hidden_posts_filter(self, queryset, name, show_hidden_posts):
            if not resolve(self.request.path).view_name.endswith("post-view-list"):
                return queryset
            if not show_hidden_posts:
                return queryset.filter(obstracts_post__processed=True)
            return queryset

        def __init__(self, data=None, *args, **kwargs):
            # if filterset is bound, use initial values as defaults
            if data is not None:
                # get a mutable copy of the QueryDict
                data = data.copy()

                for name, f in self.base_filters.items():
                    initial = f.extra.get("initial")

                    # filter param is either missing or empty, use initial as default
                    if not data.get(name) and initial != None:
                        data[name] = initial
            super().__init__(data, *args, **kwargs)

    def filter_queryset(self, queryset):
        queryset = queryset.annotate(
            job_state=Subquery(
                models.Job.objects.filter(
                    history4feed_job_id=OuterRef("last_job_id")
                ).values("state")[:1]
            )
        )
        return super().filter_queryset(queryset)

    @decorators.action(
        detail=True,
        methods=["PATCH"],
        serializer_class=serializers.CreateTaskSerializer,
    )
    def reindex(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        _, h4f_job = self.new_reindex_post_job(request)
        job = tasks.create_job_entry(h4f_job, s.validated_data["profile_id"])
        return Response(
            serializers.ObstractsJobSerializer(job).data, status=status.HTTP_201_CREATED
        )

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
            OpenApiParameter(
                "ignore_embedded_sro",
                type=bool,
                description="If set to `true` all embedded SROs are removed from the response.",
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

    def get_obstracts_file(self, fail_if_no_extraction=True) -> models.File:
        post_file: models.File = self.get_object().obstracts_post
        if fail_if_no_extraction and not post_file.processed:
            raise exceptions.NotFound(
                {
                    "error": "This post is in failed extraction state, please reindex to access"
                }
            )
        return post_file

    @extend_schema(
        summary="Get the extractions performed on this post",
        description=textwrap.dedent(
            """
            When extractions are performed, txt2stix creates an extraction file to show the values extracted, what extractor was used, how relationships between extractions were made (if AI relationship mode used), the AI summary produced (if AI summary enabled), and details about the Attack Flow order detected (if enabled).

            Use this endpoint to view this file which can be useful to understanding how the output for the post was produced.
            """
        ),
        responses={200: dict},
    )
    @decorators.action(detail=True, methods=["GET"])
    def extractions(self, request, post_id=None, **kwargs):
        post_file: models.File = self.get_obstracts_file()
        return Response(post_file.txt2stix_data or {})

    @decorators.action(
        detail=True,
        methods=["GET"],
        url_path="attack-navigator",
        serializer_class=serializers.AttackNavigatorSerializer,
    )
    def list_attack_navigators(self, request, post_id=None, **kwargs):
        post_file: models.File = self.get_obstracts_file()
        layers = (post_file.txt2stix_data or {}).get("navigator_layer") or []
        s = serializers.AttackNavigatorSerializer(
            data={layer["domain"].removesuffix("-attack"): True for layer in layers}
        )
        s.is_valid()
        return Response(s.data)

    @decorators.action(
        detail=True,
        methods=["GET"],
        url_path="attack-navigator/<attack_domain>",
        serializer_class=serializers.AttackNavigatorDomainSerializer,
    )
    def retrieve_attack_navigators(
        self, request, post_id=None, attack_domain=None, **kwargs
    ):
        if attack_domain not in ATTACK_DOMAINS:
            raise exceptions.NotFound({"error": "unknown attack domain"})
        post_file: models.File = self.get_obstracts_file()
        layers = (post_file.txt2stix_data or {}).get("navigator_layer") or []
        layers = {layer["domain"].removesuffix("-attack"): layer for layer in layers}
        if not layers.get(attack_domain):
            raise exceptions.NotFound(
                {"error": "no navigator for this domain", "domains": list(layers)}
            )
        return Response(layers[attack_domain])

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
        obj = self.get_obstracts_file(fail_if_no_extraction=True)
        if not obj.markdown_file:
            raise exceptions.NotFound("post has no associated markdown file")
        images = {
            img.name: img.file.url
            for img in models.FileImage.objects.filter(report__post_id=post_id)
        }
        resp_text = MarkdownImageReplacer.get_markdown(
            request.build_absolute_uri(),
            obj.markdown_file.read().decode(),
            images,
        )
        return FileResponse(
            streaming_content=resp_text,
            content_type="text/markdown",
            filename="markdown.md",
        )

    @extend_schema(
        responses={
            200: serializers.ImageSerializer(many=True),
            404: api_schema.DEFAULT_404_ERROR,
            400: api_schema.DEFAULT_400_ERROR,
        },
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
        queryset = models.FileImage.objects.filter(report__post_id=post_id).order_by(
            "name"
        )
        paginator = Pagination("images")

        page = paginator.paginate_queryset(queryset, request, self)

        if page is not None:
            serializer = serializers.ImageSerializer(
                page, many=True, context=dict(request=request)
            )
            return paginator.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def destroy(self, *args, **kwargs):
        obj = self.get_object()
        retval = super().destroy(*args, **kwargs)
        self.remove_report_objects(obj.obstracts_post)
        models.File.objects.filter(pk=obj.pk).delete()
        return retval

    @staticmethod
    def remove_report_objects(instance: models.File):
        instance = models.File.objects.get(pk=instance.post_id)
        db_service = ArangoDBService(
            settings.ARANGODB_DATABASE,
            [],
            [],
            create=False,
            username=settings.ARANGODB_USERNAME,
            password=settings.ARANGODB_PASSWORD,
            host_url=settings.ARANGODB_HOST_URL,
        )
        helper = ArangoDBHelper(settings.VIEW_NAME, None)
        bind_vars = {
            "post_id": str(instance.post_id),
            "@vertex": instance.feed.vertex_collection,
            "@edge": instance.feed.edge_collection,
        }
        query = """
        LET removed_edges = (
            FOR de IN @@edge
            FILTER de._obstracts_post_id == @post_id
            RETURN [de._key, de.id]
        )

        LET removed_vertices = (
            FOR dv IN @@vertex
            FILTER dv._obstracts_post_id == @post_id
            RETURN [dv._key, dv.id]
        )
        RETURN [removed_vertices, removed_edges]
        """
        removed_vertices, removed_edges = helper.execute_query(
            query, bind_vars=bind_vars, paginate=False
        )[0]

        for collection, objects in [
            (instance.feed.vertex_collection, removed_vertices),
            (instance.feed.edge_collection, removed_edges),
        ]:
            helper.db.collection(collection).delete_many(
                [dict(_key=x[0]) for x in objects], silent=True
            )
            db_service.update_is_latest_several_chunked(
                [x[1] for x in objects],
                collection,
                collection.removesuffix("_vertex_collection").removesuffix(
                    "_edge_collection"
                )
                + "_edge_collection",
            )

    def get_post_objects(self, post_id):
        post_file: models.File = self.get_obstracts_file()
        helper = ArangoDBHelper(settings.ARANGODB_DATABASE_VIEW, self.request)
        types = helper.query.get("types", "")
        bind_vars = {
            "types": (
                list(OBJECT_TYPES.intersection(types.split(","))) if types else None
            ),
            "@view": settings.VIEW_NAME,
            "post_id": str(post_file.post_id),
        }
        filters = []

        if q := helper.query_as_bool("ignore_embedded_sro", default=False):
            filters.append("FILTER doc._is_ref != TRUE")

        query = """

FOR doc IN @@view
    FILTER doc._obstracts_post_id == @post_id
    FILTER NOT @types OR doc.type IN @types
    #more_filters
    
    COLLECT id = doc.id  INTO docs
    LET dd = FIRST(FOR doc IN docs[*].doc RETURN doc)
    
    LIMIT @offset, @count
    RETURN KEEP(dd, KEYS(dd, TRUE))

        """.replace(
            "#more_filters", "\n".join(filters)
        )
        return helper.execute_query(query, bind_vars=bind_vars)


@extend_schema_view(
    create=extend_schema(
        request=serializers.PostCreateSerializer,
        responses={
            201: ObstractsJobSerializer,
            404: api_schema.DEFAULT_404_ERROR,
            400: api_schema.DEFAULT_400_ERROR,
        },
        summary="Manually add a Post to A Feed",
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
    reindex_feed=extend_schema(
        summary="Update all Posts in a feed",
        description=textwrap.dedent(
            """
                This endpoint will re-index the Post content (`description`) for all Post IDs currently listed in the Feed.

                The following key/values are accepted in the body of the request:

                * profile_id (required - valid Profile ID): You get the last `profile_id` used for this feed using the Get Jobs endpoint and post ID. Changing the profile will potentially change data extracted from each post on re-index.

                This update change the content (`description`) stored for the Post and rerun the extractions on the new content for the Post.

                It will not update the `title`, `pubdate`, `author`, or `categories`. If you need to update these properties you can use the Update Post Metadata endpoint.

                **IMPORTANT**: This action will delete the original post as well as all the STIX SDO and SRO objects created during the processing of the original text. Mostly this is not an issue, however, if the post has been removed at source you will end up with an empty entry for this Post.

                Note, if you only want to update the content of a single post, it is much more efficient to use the Update a Post in a Feed endpoint.

                The response will return the Job information responsible for getting the requested data you can track using the id returned via the GET Jobs by ID endpoint.
            """
        ),
        responses={
            201: ObstractsJobSerializer,
            404: api_schema.DEFAULT_404_ERROR,
            400: api_schema.DEFAULT_400_ERROR,
        },
        request=serializers.CreateTaskSerializer,
    ),
)
class FeedPostView(h4f_views.feed_post_view, PostOnlyView):
    schema = ObstractsAutoSchema()
    serializer_class = serializers.PostWithFeedIDSerializer

    openapi_tags = ["Posts (by Feed)"]

    class filterset_class(PostOnlyView.filterset_class):
        feed_id = None

    def create(self, request, *args, **kwargs):
        s = serializers.FetchFeedSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        h4f_job = self.new_create_post_job(request, self.kwargs["feed_id"])
        job = tasks.create_job_entry(h4f_job, s.validated_data["profile_id"])
        return Response(
            ObstractsJobSerializer(job).data, status=status.HTTP_201_CREATED
        )

    @decorators.action(methods=["PATCH"], detail=False, url_path="reindex")
    def reindex_feed(self, request, *args, feed_id=None, **kwargs):
        s = serializers.CreateTaskSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        h4f_job = self.new_reindex_feed_job(feed_id)
        job = tasks.create_job_entry(h4f_job, s.validated_data["profile_id"])
        return Response(
            ObstractsJobSerializer(job).data, status=status.HTTP_201_CREATED
        )


class RSSView(h4f_views.RSSView):
    class filterset_class(PostOnlyView.filterset_class):
        feed_id = None


@extend_schema_view(
    list=extend_schema(
        summary="Search Extraction Jobs",
        description=textwrap.dedent(
            """
            Jobs track the status of the request to get posts for Feeds. For every new Feed added and every update to a Feed requested a job will be created. The id of a job is printed in the POST and PATCH responses respectively, but you can use this endpoint to search for the id again, if required.
            """
        ),
        responses={400: api_schema.DEFAULT_400_ERROR, 200: ObstractsJobSerializer},
    ),
    retrieve=extend_schema(
        summary="Get an Extraction Job",
        description=textwrap.dedent(
            """
            Using a Job ID you can retrieve information about its state via this endpoint. This is useful to see if a Job to get data is complete, how many posts were imported in the job, or if an error has occurred.
            """
        ),
        responses={404: api_schema.DEFAULT_404_ERROR, 200: ObstractsJobSerializer},
    ),
    cancel_job=extend_schema(
        summary="Kill a running Job that is performing extractions on Posts",
        description=textwrap.dedent(
            """
            Using a Job ID you can kill it whilst it is still in `running` or `pending` state.

            After the history4feed job (`h4f_jobs`) has completed indexing all Post content, the extraction job is triggered. This is what this endpoint covers.

            If posts in the job have already had extractions completed before the entire job is complete, they will still remain and you will need to delete them using the delete endpoints manually.

            The job will enter `cancelled` state when cancelled.

            This endpoint is especially useful when errors are detected on first backfill where errors are detected. By killing the job, it ensures no more requests to external services are made (e.g. AI providers), thus saving potential costs involved in completing what has been identified as an erroneous job.
            """
        ),
        responses={
            204: {},
            404: api_schema.DEFAULT_404_ERROR,
        },
    ),
)
class JobView(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    schema = ObstractsAutoSchema()
    serializer_class = ObstractsJobSerializer
    openapi_tags = ["Jobs"]
    lookup_url_kwarg = "job_id"
    filter_backends = [DjangoFilterBackend, Ordering]
    ordering_fields = ["created"]
    ordering = "created_descending"
    pagination_class = Pagination("jobs")

    class filterset_class(FilterSet):
        feed_id = BaseCSVFilter(
            label="Filter by Feed ID (e.g. `6c6e6448-04d4-42a3-9214-4f0f7d02694e`.",
            lookup_expr="in",
        )
        state = Filter(
            label="Filter by state.",
        )
        post_id = UUIDFilter(
            label="Filter by Post ID",
            field_name="history4feed_job__fulltext_jobs__post_id",
        )

    def get_queryset(self):
        return models.Job.objects

    @decorators.action(methods=["DELETE"], detail=True, url_path="kill")
    def cancel_job(self, request, *args, **kwargs):
        obj: models.Job = self.get_object()
        obj.cancel()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    responses={204: {}},
    tags=["Server Status"],
    summary="Check if the service is running",
    description=textwrap.dedent(
        """
        If this endpoint returns a 204, the service is running as expected.
        """
    ),
)
@decorators.api_view(["GET"])
def health_check(request):
    return Response(status=status.HTTP_204_NO_CONTENT)
