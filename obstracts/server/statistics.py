import logging
import textwrap
from datetime import UTC, datetime, timedelta

from django.utils import timezone
from django.db.models import Count, Subquery

from rest_framework import serializers, viewsets, exceptions
from rest_framework.response import Response

from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_serializer
from obstracts.server.models import ObjectValue, File, h4f_models
from obstracts.server import autoschema as api_schema
from django.core.cache import cache


STATISTICS_KNOWLEDGEBASES = {
    "enterprise-attack": "Top 10 Enterprise ATT&CK Techniques",
    "mobile-attack": "Top 10 Mobile ATT&CK Techniques",
    "ics-attack": "Top 10 ICS ATT&CK Techniques",
    "location": "Top 10 Locations",
    "capec": "Top 10 CAPECs",
    "cve": "Top 10 CVEs",
    "sector": "Top 10 Sectors",
    "cwe": "Top 10 CWEs",
    "disarm": "Top 10 DISARM Objects",
    "atlas": "Top 10 ATLAS Objects",
    "sector": "Top 10 Sectors",
}
CACHE_KEY = "statistics-cache"
EXPIRE_MINUTES = 60
MAX_TIME_BEFORE_REFRESH = 45

def _top10(knowledgebase: str, since: datetime, until: datetime):
    """Return top 10 stix_ids for a given knowledgebase and time window, ranked by occurrence count."""
    return (
        ObjectValue.objects.filter(
            knowledgebase=knowledgebase,
            file__post__pubdate__gte=since,
            file__post__pubdate__lt=until,
            file__post__deleted_manually=False,
        )
        .values("stix_id", "values")
        .annotate(count=Count("file__post_id", distinct=True))
        .order_by("-count")[:10]
    )

def _build_category(category_label: str, knowledgebase: str, now: datetime, days: int):
    since = now - timedelta(days=days)
    return {
        "label": category_label,
        "knowledgebase": knowledgebase,
        "results": [
            {"stix_id": row["stix_id"], "values": row["values"], "count": row["count"]}
            for row in _top10(knowledgebase, since, now)
        ],
    }

def _build_categories(now: datetime, days: int, category_labels=STATISTICS_KNOWLEDGEBASES):
    data = cache.get(CACHE_KEY)
    if not data:
        build_data_and_add_to_cache(now)
        return _build_categories(now, days, category_labels)
    return data['time'], [
        data[days][knowledgebase] for knowledgebase in category_labels
    ]

def ensure_statistics_data(now: datetime):
    now_ts = now.timestamp()
    data = cache.get(CACHE_KEY)
    if not data:
        build_data_and_add_to_cache(now)
        return ensure_statistics_data(now)
    if data['time'] - now_ts > (60 * MAX_TIME_BEFORE_REFRESH):
        build_data_and_add_to_cache(now)
        return ensure_statistics_data(now)
    return data
    

def _build_data_for_categories(now, days, category_labels):
    return {
        knowledgebase: _build_category(STATISTICS_KNOWLEDGEBASES[knowledgebase], knowledgebase, now, days)
        for knowledgebase in category_labels
    }

def build_data_and_add_to_cache(now: datetime):
    logging.info("re-Building statistics cache")
    data_7_days = _build_data_for_categories(now, 7, STATISTICS_KNOWLEDGEBASES)
    data_30_days = _build_data_for_categories(now, 30, STATISTICS_KNOWLEDGEBASES)
    cache.set(CACHE_KEY, {7: data_7_days, 30: data_30_days, "time": now.timestamp()}, timeout=60*EXPIRE_MINUTES)
    return 

class TrendingEntrySerializer(serializers.Serializer):
    stix_id = serializers.CharField()
    values = serializers.JSONField()
    count = serializers.IntegerField(help_text="Number of posts in this period containing this object.")


class TrendingCategorySerializer(serializers.Serializer):
    label = serializers.CharField(help_text="Human-readable label for this category.")
    knowledgebase = serializers.CharField(help_text="The knowledgebase value used to filter ObjectValues.")
    results = TrendingEntrySerializer(many=True)


class PeriodSerializer(serializers.Serializer):
    period_days = serializers.IntegerField()
    period_start = serializers.DateTimeField()
    period_end = serializers.DateTimeField()
    categories = TrendingCategorySerializer(many=True)


@extend_schema_serializer(many=False)
class StatisticsResponseSerializer(serializers.Serializer):
    last_7_days = PeriodSerializer()
    last_30_days = PeriodSerializer()


class StatisticsView(viewsets.ViewSet):
    openapi_tags = ["Statistics"]
    lookup_url_kwarg = "knowledgebase"



    @extend_schema(
        summary="Get trending TTP statistics",
        description=textwrap.dedent(
            """
            Returns the top 10 most-seen objects for each of the following TTP categories,
            for both the last 7 days and the last 30 days, ranked by the number of distinct
            posts in which they appeared:

            * **Enterprise ATT&CK Techniques** (`enterprise-attack`)
            * **CVEs** (`cve`)
            * **Sectors** (`sector`)
            * **CWEs** (`cwe`)
            * **Mobile ATT&CK Techniques** (`mobile-attack`)
            * **ICS ATT&CK Techniques** (`ics-attack`)
            * **Locations** (`location`)
            * **CAPECs** (`capec`)
            """
        ),
        responses={200: StatisticsResponseSerializer, 400: api_schema.DEFAULT_400_ERROR},
        parameters=[
            OpenApiParameter(
                name="knowledgebase",
                description="Optional filter to return statistics for only a specific knowledgebase category (e.g. `enterprise-attack` or `cve`). If not provided, statistics for all categories will be returned.",
                required=False,
                enum=list(STATISTICS_KNOWLEDGEBASES.keys()),
            )
        ]
    )
    def list(self, request):
        now = timezone.now()
        knowledgebases = list(STATISTICS_KNOWLEDGEBASES.keys())
        if "knowledgebase" in request.query_params:
            kb_filter = request.query_params["knowledgebase"]
            if kb_filter not in knowledgebases:
                raise exceptions.ValidationError(f"Invalid knowledgebase filter: {kb_filter}")
            knowledgebases = [kb_filter]


        def _period(now, days):
            now, value = _build_categories(now, days, category_labels=knowledgebases)
            now = datetime.fromtimestamp(now, tz=UTC)
            return {
                "period_days": days,
                "period_start": now - timedelta(days=days),
                "period_end": now,
                "categories": value,
            }

        data = {
            "last_7_days": _period(now, 7),
            "last_30_days": _period(now, 30),
        }
        return Response(StatisticsResponseSerializer(data).data)
