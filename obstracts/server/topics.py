import textwrap
import uuid

from django.db.models import Count
from django_filters.rest_framework import FilterSet, filters
from drf_spectacular.utils import extend_schema, extend_schema_field, extend_schema_view
from rest_framework import decorators, mixins, status, viewsets, serializers
from rest_framework.response import Response
from obstracts.server.serializers import ObstractsJobSerializer

from obstracts.classifier.models import Cluster
from obstracts.cjob import tasks

from . import autoschema as api_schema
from . import models
from .autoschema import ObstractsAutoSchema
from .utils import Pagination, Ordering
from django_filters.rest_framework import DjangoFilterBackend


class TopicBaseSerializer(serializers.ModelSerializer):

    class Meta:
        model = Cluster
        exclude = ["members", "created_at"]


class TopicSerializer(TopicBaseSerializer):
    posts_count = serializers.IntegerField(read_only=True, required=False)


class TopicPostSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="pk")
    title = serializers.CharField(source="post.title")

    class Meta:
        model = models.File
        fields = ["id", "title", "feed_id"]


class TopicBuildSerializer(serializers.Serializer):
    force = serializers.BooleanField(default=False, help_text="Force regeneration even when embeddings/clusters already exist.")


@extend_schema_view(
    list=extend_schema(
        summary="Search Topics",
        description=textwrap.dedent(
            """
            Returns all topics (clusters) produced by the classifier. Use the `label`
            filter for a case-insensitive partial-match search on the topic label.
            """
        ),
        responses={
            200: TopicSerializer,
            400: api_schema.DEFAULT_400_ERROR,
        },
    ),
    retrieve=extend_schema(
        summary="Get a Topic",
        description=textwrap.dedent(
            """
            Returns a single topic by its UUID, including the list of posts
            that belong to that topic.
            """
        ),
    ),
    build_clusters=extend_schema(
        summary="Build topic clusters",
        description=textwrap.dedent(
            """
            When a new post is added, the existing clusters remain fixed and the app predicts where a new point would land, instead of changing the clusters every time.

            This will create a background job that runs topic clustering from available embeddings.

            The following parameters are available to pass in the body;

            * `force` (boolean, default `false`), setting to `true` will force a regeneration of clusters across all indexed posts. Note, post topic IDs will change. You should only run as `true` if you want to destroy everything that exists, else `false` will regenerate the clusters but persist old topics.
            """
        ),
        request=TopicBuildSerializer,
        responses={201: ObstractsJobSerializer, 400: api_schema.DEFAULT_400_ERROR},
    ),
)
class TopicView(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    openapi_tags = ["Topics"]
    schema = ObstractsAutoSchema()
    pagination_class = Pagination("topics")
    lookup_url_kwarg = "topic_id"
    filter_backends = [DjangoFilterBackend, Ordering]
    ordering_fields = ["label", "posts_count"]
    ordering = "posts_count_descending"
    serializer_class = TopicSerializer


    class filterset_class(FilterSet):
        label = filters.CharFilter(
            field_name="label",
            lookup_expr="icontains",
            help_text="Case-insensitive partial match search on topic label.",
        )

    def get_queryset(self):
        qs = Cluster.objects.annotate(
            posts_count=Count("members__file", distinct=True),
        )
        return qs


    @decorators.action(methods=["PATCH"], detail=False, url_path="build_clusters")
    def build_clusters(self, request, *args, **kwargs):
        from .serializers import ObstractsJobSerializer

        s = TopicBuildSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        job = models.Job.objects.create(
            id=uuid.uuid4(),
            type=models.JobType.BUILD_CLUSTERS,
            state=models.JobState.PROCESSING,
        )
        t = tasks.build_topic_clusters.si(
            job.id,
            force=s.validated_data["force"],
        )
        t.apply_async()
        obj = models.Job.objects.get(id=job.id)
        return Response(ObstractsJobSerializer(obj).data, status=status.HTTP_201_CREATED)
