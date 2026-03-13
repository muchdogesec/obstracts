import textwrap
from datetime import datetime, timedelta

from django.utils import timezone
from django.db.models import Count

from rest_framework import serializers, viewsets
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema, extend_schema_serializer
from obstracts.server.models import ObjectValue


STATISTICS_TTP_TYPES = {
    "enterprise-attack": "Top 10 ATT&CK Techniques",
    "cve": "Top 10 CVEs",
    "sector": "Top 10 Sectors",
    "cwe": "Top 10 CWEs",
}


def _top10(ttp_type: str, since: datetime, until: datetime):
    """Return top 10 stix_ids for a given ttp_type and time window, ranked by occurrence count."""
    return (
        ObjectValue.objects.filter(
            ttp_type=ttp_type,
            file__post__pubdate__gte=since,
            file__post__pubdate__lt=until,
        )
        .values("stix_id", "values")
        .annotate(count=Count("file__post_id", distinct=True))
        .order_by("-count")[:10]
    )


def _build_categories(now: datetime, days: int):
    since = now - timedelta(days=days)
    return [
        {
            "label": label,
            "ttp_type": ttp_type,
            "results": [
                {"stix_id": row["stix_id"], "values": row["values"], "count": row["count"]}
                for row in _top10(ttp_type, since, now)
            ],
        }
        for ttp_type, label in STATISTICS_TTP_TYPES.items()
    ]


class TrendingEntrySerializer(serializers.Serializer):
    stix_id = serializers.CharField()
    values = serializers.JSONField()
    count = serializers.IntegerField(help_text="Number of posts in this period containing this object.")


class TrendingCategorySerializer(serializers.Serializer):
    label = serializers.CharField(help_text="Human-readable label for this category.")
    ttp_type = serializers.CharField(help_text="The ttp_type value used to filter ObjectValues.")
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

    @extend_schema(
        summary="Get trending TTP statistics",
        description=textwrap.dedent(
            """
            Returns the top 10 most-seen objects for each of the following TTP categories,
            for both the last 7 days and the last 30 days, ranked by the number of distinct
            posts in which they appeared:

            * **ATT&CK Techniques** (`enterprise-attack`)
            * **CVEs** (`cve`)
            * **Sectors** (`sector`)
            * **CWEs** (`cwe`)
            """
        ),
        responses={200: StatisticsResponseSerializer},
    )
    def list(self, request):
        now = timezone.now()

        def _period(days):
            return {
                "period_days": days,
                "period_start": now - timedelta(days=days),
                "period_end": now,
                "categories": _build_categories(now, days),
            }

        data = {
            "last_7_days": _period(7),
            "last_30_days": _period(30),
        }
        return Response(StatisticsResponseSerializer(data).data)
