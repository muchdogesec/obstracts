import textwrap
from rest_framework import viewsets, filters, mixins
from rest_framework.response import Response
from django_filters.rest_framework import (
    DjangoFilterBackend,
    FilterSet,
    CharFilter,
    MultipleChoiceFilter,
    BooleanFilter,
    BaseCSVFilter,
)
from django_filters.fields import ChoiceField
from obstracts.server import autoschema as api_schema

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from django.db.models import F, Value, JSONField as DjangoJSONField, Min, Max
from django.db.models.functions import JSONObject
from django.contrib.postgres.aggregates import ArrayAgg


from obstracts.server.models import ObjectValue
from obstracts.server.utils import Pagination
from obstracts.server.values.values import sco_value_map, sdo_value_map
from .serializers import ObjectValueSerializer
from dogesec_commons.utils.ordering import Ordering

TTP_TYPES = [
    "cve",
    "cwe",
    "location",
    "enterprise-attack",
    "mobile-attack",
    "ics-attack",
    "capec",
    "atlas",
    "disarm",
    "sector",
]


class ChoiceCSVFilter(BaseCSVFilter):
    field_class = ChoiceField

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("lookup_expr", "in")
        super().__init__(*args, **kwargs)


class ObjectValueFilterSet(FilterSet):
    """Base filterset for ObjectValue queries."""

    id = CharFilter(
        field_name="stix_id",
        lookup_expr="exact",
        help_text="Filter by exact STIX object ID. e.g. `ipv4-addr--ba6b3f21-d818-4e7c-bfff-765805177512`, `indicator--7bff059e-6963-4b50-b901-4aba20ce1c01`",
    )
    post_id = CharFilter(
        field_name="file__post_id",
        help_text="Filter the results to only contain objects present in the specified Post ID. Get a Post ID using the Feeds endpoints.",
    )
    value = CharFilter(
        method="filter_value",
        help_text="Search within all extracted values using full-text search. This is the IoC or meaningful data extracted from the object. Search is wildcard. For example, `1.1` will return objects with values containing `1.1.1.1`, `2.1.1.2`, etc. Searches across all value fields for the object type.",
    )
    value_exact = BooleanFilter(
        method="filter_noop",
        help_text="Set to `true` to only return exact matches on the `value` field. Default behaviour is wildcard search.",
    )
    feed_id = CharFilter(
        field_name="file__feed__feed_id",
        help_text="Filter the results to only contain objects present in posts from the specified Feed ID. Get a Feed ID using the Feeds endpoints.",
    )

    def filter_value(self, queryset, name, value):
        """
        Filter by value field, using exact or wildcard matching based on value_exact parameter.
        """
        if not value:
            return queryset

        # Check if value_exact is set to True
        value_exact = self.data.get("value_exact", "false").lower() == "true"

        if value_exact:
            return queryset.filter(values__jsonb_vexact=value)
        else:
            return queryset.filter(values__jsonb_vcontains=value)

    def filter_noop(self, queryset, name, value):
        """
        No-op filter for value_exact - it's handled by filter_value method.
        """
        return queryset


@extend_schema_view(
    list=extend_schema(
        responses={
            200: ObjectValueSerializer,
            400: api_schema.DEFAULT_400_ERROR
        },
        
    )
)
class BaseObjectValueView(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Base view for ObjectValue queries with common functionality."""

    queryset = ObjectValue.objects.all()
    serializer_class = ObjectValueSerializer
    pagination_class = Pagination("values")
    filter_backends = [DjangoFilterBackend, Ordering]
    filterset_class = ObjectValueFilterSet
    ordering_fields = ["stix_id", "type", "ttp_type"]
    ordering = "stix_id_descending"
    openapi_tags = ["Object Values"]

    # Override in subclasses to filter by type
    allowed_types = None

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by allowed types if specified
        if self.allowed_types:
            queryset = queryset.filter(type__in=self.allowed_types)

        # Aggregate all post_ids for each unique stix_id
        queryset = queryset.values("stix_id").annotate(
            type=F("type"),
            ttp_type=F("ttp_type"),
            values=F("values"),
            matched_posts=ArrayAgg("file__post_id", distinct=True),
            created=Min("created"),
            modified=Max("modified"),
        )

        return queryset


@extend_schema_view(
    list=extend_schema(
        summary="Search and filter STIX Cyber Observable Objects",
        description=textwrap.dedent(
            """
            Search for STIX Cyber Observable Objects (aka Indicators of Compromise). If you have the object ID already, you can use the base GET Objects endpoint.

            The `value` filter searches all extracted fields from the object, including:

            * `artifact.url`, `artifact.mime_type`
            * `autonomous-system.number`, `autonomous-system.name`
            * `directory.path`
            * `domain-name.value`
            * `email-addr.value`
            * `email-message.subject`, `email-message.body`, `email-message.message_id`
            * `file.name` and file hashes
            * `ipv4-addr.value`
            * `ipv6-addr.value`
            * `mac-addr.value`
            * `mutex.name`
            * `network-traffic.protocols`
            * `process.command_line`, `process.cwd`
            * `software.name`, `software.cpe`, `software.vendor`, `software.version`
            * `url.value`
            * `user-account.user_id`, `user-account.account_login`, `user-account.account_type`
            * `windows-registry-key.key`
            * `x509-certificate.subject`, `x509-certificate.issuer`, `x509-certificate.serial_number`

            Results are deduplicated by `stix_id`, with all associated `post_id`s aggregated in the `matched_posts` field.
            """
        ),
    ),
)
class SCOValueView(BaseObjectValueView):
    """View for STIX Cyber Observable Objects (SCOs) only."""

    allowed_types = list(sco_value_map.keys())
    ordering_fields = ["values", "stix_id", "type"]
    ordering = "values_ascending"

    class filterset_class(ObjectValueFilterSet):
        types = ChoiceCSVFilter(
            field_name="type",
            help_text="Filter the results by one or more STIX SCO Object types",
            choices=[(c, c) for c in sco_value_map.keys()],
        )


@extend_schema_view(
    list=extend_schema(
        summary="Search and filter STIX Domain Objects",
        description=textwrap.dedent(
            """
            Search for STIX Domain Objects (aka TTPs). If you have the object ID already, you can use the base GET Objects endpoint.

            The `value` filter searches all extracted name and descriptive fields from the object, including:

            * `attack-pattern.name`, `attack-pattern.aliases`
            * `campaign.name`, `campaign.aliases`
            * `course-of-action.name`
            * `grouping.name`, `grouping.context`
            * `identity.name`
            * `incident.name`
            * `indicator.name`, `indicator.pattern`
            * `infrastructure.name`
            * `intrusion-set.name`, `intrusion-set.aliases`
            * `location.name`, `location.country`, `location.region`
            * `malware.name`, `malware.x_mitre_aliases`
            * `malware-analysis.product`, `malware-analysis.version`
            * `note.abstract`, `note.content`
            * `observed-data.objects`
            * `opinion.explanation`, `opinion.opinion`
            * `report.name`
            * `threat-actor.name`
            * `tool.name`, `tool.tool_version`, `tool.x_mitre_aliases`
            * `vulnerability.name`
            * MITRE ATT&CK objects: `x-mitre-analytic`, `x-mitre-asset`, `x-mitre-collection`, `x-mitre-data-component`, `x-mitre-data-source`, `x-mitre-detection-strategy`, `x-mitre-matrix`, `x-mitre-tactic`

            Results are deduplicated by `stix_id`, with all associated `post_id`s aggregated in the `matched_posts` field.
            """
        ),
    ),
)
class SDOValueView(BaseObjectValueView):
    """View for STIX Domain Objects (SDOs) only."""

    allowed_types = list(sdo_value_map.keys())
    ordering_fields = ["stix_id", "type", "ttp_type", "values", "created", "modified"]

    class filterset_class(ObjectValueFilterSet):
        ttp_types = ChoiceCSVFilter(
            field_name="ttp_type",
            help_text="Filter results by source of TTP object (cve, cwe, enterprise-attack, mobile-attack, ics-attack, capec, location, disarm, atlas, sector)",
            choices=[(c, c) for c in TTP_TYPES],
        )
        types = ChoiceCSVFilter(
            field_name="type",
            help_text="Filter the results by one or more STIX Domain Object types",
            choices=[(c, c) for c in sdo_value_map.keys()],
        )
