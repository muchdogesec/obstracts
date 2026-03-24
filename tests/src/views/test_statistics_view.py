"""
Tests for the Statistics endpoint (GET /api/v1/statistics/).

Verifies that:
- The response shape contains both last_7_days and last_30_days periods.
- Each period has the expected categories with correct knowledgebase values.
- Counts reflect only posts whose pubdate falls within the period window.
- Objects outside the time window are not counted.
- The top-10 ordering is by descending count.
"""

import pytest
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APIClient

from history4feed.app import models as h4f_models
from obstracts.server.models import File, ObjectValue
from dogesec_commons.stixifier.models import Profile


EXPECTED_CATEGORIES = ["enterprise-attack", "cve", "sector", "cwe"]
STATISTICS_URL = "/api/v1/statistics/"


def _make_post(feed, title, pubdate, link_suffix, post_id):
    return h4f_models.Post.objects.create(
        feed=feed,
        title=title,
        pubdate=pubdate,
        id=post_id,
        link=f"https://stats-test.example.com/{link_suffix}",
        is_full_text=True,
    )


def _make_file(feed_profile, post, profile):
    return File.objects.create(
        feed=feed_profile,
        post=post,
        processed=True,
        summary="stats test post",
        profile=profile,
    )


@pytest.fixture
def stats_data(stixifier_profile):
    """
    Creates a feed with posts spread across three time windows:
      - within_7d  : 3 days ago  → inside both 7-day and 30-day windows
      - within_30d : 20 days ago → inside 30-day window only
      - outside    : 40 days ago → outside both windows

    ObjectValues created:
      - "enterprise-attack" stix_id A: files within_7d[0], within_7d[1], within_30d[0]
        → 7-day count=2, 30-day count=3
      - "enterprise-attack" stix_id B: file within_7d[0]
        → 7-day count=1, 30-day count=1
      - "cve" stix_id C: file within_7d[0]
        → 7-day count=1, 30-day count=1
      - "sector" stix_id D: file within_30d[0]
        → 7-day count=0 (absent), 30-day count=1
      - "cwe" stix_id E: file outside[0]
        → 7-day count=0 (absent), 30-day count=0 (absent)
    """
    now = timezone.now()

    h4f_feed = h4f_models.Feed.objects.create(
        title="Stats Test Feed",
        url="https://stats-test.example.com/rss",
        id="a1b2c3d4-1111-4111-8111-000000000001",
    )
    feed_profile = h4f_feed.obstracts_feed

    # ── posts within 7-day window ──────────────────────────────────────────────
    post_7a = _make_post(h4f_feed, "7d Post A", now - timedelta(days=3),
                         "7a", "a1b2c3d4-1111-4111-8111-000000000011")
    post_7b = _make_post(h4f_feed, "7d Post B", now - timedelta(days=5),
                         "7b", "a1b2c3d4-1111-4111-8111-000000000012")

    # ── post within 30-day but outside 7-day window ───────────────────────────
    post_30a = _make_post(h4f_feed, "30d Post A", now - timedelta(days=20),
                          "30a", "a1b2c3d4-1111-4111-8111-000000000021")

    # ── post outside both windows ─────────────────────────────────────────────
    post_old = _make_post(h4f_feed, "Old Post", now - timedelta(days=40),
                          "old", "a1b2c3d4-1111-4111-8111-000000000031")

    file_7a  = _make_file(feed_profile, post_7a,  stixifier_profile)
    file_7b  = _make_file(feed_profile, post_7b,  stixifier_profile)
    file_30a = _make_file(feed_profile, post_30a, stixifier_profile)
    file_old = _make_file(feed_profile, post_old, stixifier_profile)

    # ── enterprise-attack object A (appears in 2 ×7d posts + 1 ×30d post) ────
    for f in [file_7a, file_7b, file_30a]:
        ObjectValue.objects.create(
            stix_id="attack-pattern--aaaaaaaa-0000-0000-0000-000000000001",
            type="attack-pattern",
            knowledgebase="enterprise-attack",
            values={"name": "Technique A", "aliases": ["T9000"]},
            file=f,
            created=now,
            modified=now,
        )

    # ── enterprise-attack object B (appears in 1 ×7d post only) ─────────────
    ObjectValue.objects.create(
        stix_id="attack-pattern--bbbbbbbb-0000-0000-0000-000000000002",
        type="attack-pattern",
        knowledgebase="enterprise-attack",
        values={"name": "Technique B", "aliases": ["T9001"]},
        file=file_7a,
        created=now,
        modified=now,
    )

    # ── cve object C (appears in 1 ×7d post) ─────────────────────────────────
    ObjectValue.objects.create(
        stix_id="vulnerability--cccccccc-0000-0000-0000-000000000003",
        type="vulnerability",
        knowledgebase="cve",
        values={"name": "CVE-2099-99999"},
        file=file_7a,
        created=now,
        modified=now,
    )

    # ── sector object D (appears only in 30d post, outside 7d) ───────────────
    ObjectValue.objects.create(
        stix_id="identity--dddddddd-0000-0000-0000-000000000004",
        type="identity",
        knowledgebase="sector",
        values={"name": "Finance"},
        file=file_30a,
        created=now,
        modified=now,
    )

    # ── cwe object E (appears only in old post, outside both windows) ─────────
    ObjectValue.objects.create(
        stix_id="weakness--eeeeeeee-0000-0000-0000-000000000005",
        type="weakness",
        knowledgebase="cwe",
        values={"name": "CWE-79"},
        file=file_old,
        created=now,
        modified=now,
    )

    return {
        "feed_profile": feed_profile,
        "files": {"7a": file_7a, "7b": file_7b, "30a": file_30a, "old": file_old},
    }


@pytest.mark.django_db
class TestStatisticsView:

    def test_response_200(self, client, stats_data):
        """Endpoint returns HTTP 200."""
        resp = client.get(STATISTICS_URL)
        assert resp.status_code == 200

    def test_top_level_keys(self, client, stats_data):
        """Response has exactly last_7_days and last_30_days keys."""
        data = client.get(STATISTICS_URL).json()
        assert set(data.keys()) == {"last_7_days", "last_30_days"}

    def test_period_shape(self, client, stats_data):
        """Each period object has the expected keys."""
        data = client.get(STATISTICS_URL).json()
        for key in ("last_7_days", "last_30_days"):
            period = data[key]
            assert "period_days" in period
            assert "period_start" in period
            assert "period_end" in period
            assert "categories" in period

    def test_period_days_values(self, client, stats_data):
        """period_days matches the expected number of days."""
        data = client.get(STATISTICS_URL).json()
        assert data["last_7_days"]["period_days"] == 7
        assert data["last_30_days"]["period_days"] == 30

    def test_categories_present(self, client, stats_data):
        """All four expected knowledgebase categories are present in each period."""
        data = client.get(STATISTICS_URL).json()
        for key in ("last_7_days", "last_30_days"):
            knowledgebases = [c["knowledgebase"] for c in data[key]["categories"]]
            for expected in EXPECTED_CATEGORIES:
                assert expected in knowledgebases, f"{expected} missing from {key}"

    def test_category_shape(self, client, stats_data):
        """Each category entry has label, knowledgebase, and results keys."""
        data = client.get(STATISTICS_URL).json()
        for category in data["last_7_days"]["categories"]:
            assert "label" in category
            assert "knowledgebase" in category
            assert "results" in category

    def test_result_entry_shape(self, client, stats_data):
        """Each result entry has stix_id, values, and count."""
        data = client.get(STATISTICS_URL).json()
        for period in ("last_7_days", "last_30_days"):
            for category in data[period]["categories"]:
                for result in category["results"]:
                    assert "stix_id" in result
                    assert "values" in result
                    assert "count" in result

    def _get_category(self, data, period_key, knowledgebase):
        return next(
            c for c in data[period_key]["categories"] if c["knowledgebase"] == knowledgebase
        )

    def test_7d_attack_count_top_entry(self, client, stats_data):
        """enterprise-attack object A should have count=2 in the 7-day period."""
        data = client.get(STATISTICS_URL).json()
        cat = self._get_category(data, "last_7_days", "enterprise-attack")
        top = cat["results"][0]
        assert top["stix_id"] == "attack-pattern--aaaaaaaa-0000-0000-0000-000000000001"
        assert top["count"] == 2

    def test_7d_attack_ordering(self, client, stats_data):
        """Results within a category are ordered by count descending."""
        data = client.get(STATISTICS_URL).json()
        cat = self._get_category(data, "last_7_days", "enterprise-attack")
        counts = [r["count"] for r in cat["results"]]
        assert counts == sorted(counts, reverse=True)

    def test_30d_attack_count_top_entry(self, client, stats_data):
        """enterprise-attack object A should have count=3 in the 30-day period."""
        data = client.get(STATISTICS_URL).json()
        cat = self._get_category(data, "last_30_days", "enterprise-attack")
        top = cat["results"][0]
        assert top["stix_id"] == "attack-pattern--aaaaaaaa-0000-0000-0000-000000000001"
        assert top["count"] == 3

    def test_7d_cve_count(self, client, stats_data):
        """CVE object should appear once in the 7-day window."""
        data = client.get(STATISTICS_URL).json()
        cat = self._get_category(data, "last_7_days", "cve")
        assert len(cat["results"]) == 1
        assert cat["results"][0]["count"] == 1

    def test_sector_absent_from_7d(self, client, stats_data):
        """Sector object posted 20 days ago should not appear in the 7-day window."""
        data = client.get(STATISTICS_URL).json()
        cat = self._get_category(data, "last_7_days", "sector")
        assert cat["results"] == []

    def test_sector_present_in_30d(self, client, stats_data):
        """Sector object posted 20 days ago should appear in the 30-day window."""
        data = client.get(STATISTICS_URL).json()
        cat = self._get_category(data, "last_30_days", "sector")
        assert len(cat["results"]) == 1
        assert cat["results"][0]["stix_id"] == "identity--dddddddd-0000-0000-0000-000000000004"

    def test_cwe_absent_from_both_periods(self, client, stats_data):
        """CWE object posted 40 days ago should not appear in either window."""
        data = client.get(STATISTICS_URL).json()
        for period in ("last_7_days", "last_30_days"):
            cat = self._get_category(data, period, "cwe")
            assert cat["results"] == [], f"Expected no CWE results in {period}"

    def test_max_10_results_per_category(self, client, stats_data, stixifier_profile):
        """Top-10 cap: a category with more than 10 distinct objects returns at most 10."""
        now = timezone.now()
        h4f_feed = h4f_models.Feed.objects.create(
            title="Top10 Test Feed",
            url="https://top10-test.example.com/rss",
            id="b2c3d4e5-2222-4222-8222-000000000002",
        )
        feed_profile = h4f_feed.obstracts_feed

        # Create 12 unique attack-pattern objects each in a distinct post within 7 days
        for i in range(12):
            post = _make_post(
                h4f_feed,
                f"Top10 Post {i}",
                now - timedelta(days=1),
                f"top10-{i}",
                f"b2c3d4e5-2222-4222-8{i:03d}-{i:012d}",
            )
            f = _make_file(feed_profile, post, stixifier_profile)
            ObjectValue.objects.create(
                stix_id=f"attack-pattern--{i:08d}-0000-0000-0000-000000000099",
                type="attack-pattern",
                knowledgebase="enterprise-attack",
                values={"name": f"Technique {i}"},
                file=f,
                created=now,
                modified=now,
            )

        data = client.get(STATISTICS_URL).json()
        cat = self._get_category(data, "last_7_days", "enterprise-attack")
        assert len(cat["results"]) <= 10
