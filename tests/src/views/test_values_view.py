"""
Tests for Object Values endpoints (SCO and SDO views).

These tests verify the functionality of the /api/v1/values/scos/ and /api/v1/values/sdos/
endpoints which provide efficient querying of STIX object values extracted from posts.
"""

from unittest.mock import patch

import pytest
from django.utils import timezone
from obstracts.server.models import ObjectValue, File
from tests.conftest import make_feed

@pytest.fixture
def override_save_method():
    """Override the Celery task to save ObjectValues to the database immediately for testing."""
    original_save = ObjectValue.save
    with patch.object(ObjectValue, 'save', autospec=True) as mock_save:
        def new_save(self, *args, **kwargs):
            if not self.is_dupe:
                existing = ObjectValue.objects.filter(stix_id=self.stix_id)
                if self.pk:
                    existing = existing.exclude(pk=self.pk)
                self.is_dupe = existing.exists()
            return original_save(self, *args, **kwargs)
        
        mock_save.side_effect = new_save
        yield

@pytest.fixture
def feed_with_object_values(stixifier_profile, override_save_method):
    """Create a feed with posts that have ObjectValue entries."""
    feed = make_feed("6ca6ce37-1c69-4a81-8490-89c91b57e557", stixifier_profile)
    
    # Get the files created by make_feed
    files = File.objects.filter(feed=feed).order_by('post__pubdate')
    
    # Create ObjectValue entries for different STIX object types
    # SCO: IPv4 addresses
    ObjectValue.objects.create(
        stix_id="ipv4-addr--ba6b3f21-d818-4e7c-bfff-765805177512",
        type="ipv4-addr",
        knowledgebase=None,
        values={"value": "192.168.1.1"},
        file=files[0],
    )
    
    ObjectValue.objects.create(
        stix_id="ipv4-addr--ba6b3f21-d818-4e7c-bfff-765805177512",
        type="ipv4-addr",
        knowledgebase=None,
        values={"value": "192.168.1.1"},
        file=files[1],  # Same IP in different post
    )
    
    ObjectValue.objects.create(
        stix_id="ipv4-addr--cc7b4f32-e929-5c8d-cfff-876916288623",
        type="ipv4-addr",
        knowledgebase=None,
        values={"value": "10.0.0.1"},
        file=files[0],
    )
    
    # SCO: Domain names
    ObjectValue.objects.create(
        stix_id="domain-name--dd8c5e43-fa3a-6d9e-dfff-987027399734",
        type="domain-name",
        knowledgebase=None,
        values={"value": "malicious.example.com"},
        file=files[0],
    )
    
    ObjectValue.objects.create(
        stix_id="domain-name--ee9d6f54-gb4b-7e0f-efff-098138400845",
        type="domain-name",
        knowledgebase=None,
        values={"value": "phishing.example.net"},
        file=files[1],
    )
    
    # SCO: URL
    ObjectValue.objects.create(
        stix_id="url--ff0e7g65-hc5c-8f1g-ffff-109249511956",
        type="url",
        knowledgebase=None,
        values={"value": "https://malicious.example.com/payload.exe"},
        file=files[0],
    )
    
    # SDO: Attack Pattern
    ObjectValue.objects.create(
        stix_id="attack-pattern--0f4a0c76-ab2d-4cb0-85d3-3f0efb8cba4d",
        type="attack-pattern",
        knowledgebase="enterprise-attack",
        values={"name": "Spearphishing Link", "aliases": ["T1566.002"]},
        file=files[0],
        created=timezone.now(),
        modified=timezone.now(),
    )
    
    ObjectValue.objects.create(
        stix_id="attack-pattern--0f4a0c76-ab2d-4cb0-85d3-3f0efb8cba4d",
        type="attack-pattern",
        knowledgebase="enterprise-attack",
        values={"name": "Spearphishing Link", "aliases": ["T1566.002"]},
        file=files[2],  # Same attack pattern in different post
        created=timezone.now(),
        modified=timezone.now(),
    )
    
    # SDO: Malware
    ObjectValue.objects.create(
        stix_id="malware--1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
        type="malware",
        knowledgebase=None,
        values={"name": "WannaCry", "x_mitre_aliases": ["WannaCryptor", "WCry"]},
        file=files[1],
        created=timezone.now(),
        modified=timezone.now(),
    )
    
    # SDO: Vulnerability
    ObjectValue.objects.create(
        stix_id="vulnerability--2b3c4d5e-6f7a-8b9c-0d1e-2f3a4b5c6d7e",
        type="vulnerability",
        knowledgebase="cve",
        values={"name": "CVE-2021-44228"},
        file=files[0],
        created=timezone.now(),
        modified=timezone.now(),
    )
    
    # SDO: Location
    ObjectValue.objects.create(
        stix_id="location--3c4d5e6f-7a8b-9c0d-1e2f-3a4b5c6d7e8f",
        type="location",
        knowledgebase="location",
        values={"name": "United States", "country": "US", "region": "northern-america"},
        file=files[1],
        created=timezone.now(),
        modified=timezone.now(),
    )
    
    return feed


@pytest.mark.django_db
class TestSCOValueView:
    """Tests for the SCO (Cyber Observable) values endpoint."""
    
    def test_list_all_scos(self, client, feed_with_object_values):
        """Test listing all SCO values."""
        response = client.get('/api/v1/values/scos/')
        
        assert response.status_code == 200
        data = response.json()
        assert 'values' in data
        
        # Should return all unique SCO objects (5 unique IPs/domains/URLs)
        assert data['total_results_count'] == 5
        
        # Check that results are deduplicated by stix_id
        stix_ids = [obj['id'] for obj in data['values']]
        assert len(stix_ids) == len(set(stix_ids))  # All unique
    
    def test_filter_by_type(self, client, feed_with_object_values):
        """Test filtering SCOs by type."""
        response = client.get('/api/v1/values/scos/?types=ipv4-addr')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return only IPv4 addresses (2 unique)
        assert data['total_results_count'] == 2
        for obj in data['values']:
            assert obj['type'] == 'ipv4-addr'
    
    def test_filter_by_multiple_types(self, client, feed_with_object_values):
        """Test filtering by multiple types."""
        response = client.get('/api/v1/values/scos/?types=ipv4-addr,domain-name')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return IPv4 (2) + domain-name (2) = 4 objects
        assert data['total_results_count'] == 4
        types = [obj['type'] for obj in data['values']]
        assert all(t in ['ipv4-addr', 'domain-name'] for t in types)
    
    def test_filter_by_value_wildcard(self, client, feed_with_object_values):
        """Test default search uses vcontains for substring matching."""
        response = client.get('/api/v1/values/scos/?value=192.168')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return the 192.168.1.1 IP using substring matching
        assert data['total_results_count'] == 1
        assert data['values'][0]['values']['value'] == '192.168.1.1'
    
    def test_filter_by_value_exact(self, client, feed_with_object_values):
        """Test value_exact matches exact individual values only."""
        response = client.get('/api/v1/values/scos/?value=192.168.1.1&value_exact=true')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return the IP with exact value match
        assert data['total_results_count'] == 1
        assert data['values'][0]['values']['value'] == '192.168.1.1'
    
    def test_filter_by_value_exact_no_substring_match(self, client, feed_with_object_values):
        """Test that exact match does NOT match substrings - only exact individual values."""
        response = client.get('/api/v1/values/scos/?value=192.168&value_exact=true')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return nothing since '192.168' is not an exact match for any individual value
        assert data['total_results_count'] == 0
    
    def test_filter_by_post_id(self, client, feed_with_object_values):
        """Test filtering by post ID."""

        # Get first post's ID
        feed = feed_with_object_values
        first_file = File.objects.filter(feed=feed).order_by('post__pubdate').first()
        post_id = first_file.post_id
        
        response = client.get(f'/api/v1/values/scos/?post_id={post_id}')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return objects from first post (4 SCOs in first post, but 1 IP is duplicated)
        # So we should have 4 unique objects (2 IPs, 1 domain, 1 URL)
        assert data['total_results_count'] == 4
        
    
    def test_filter_by_feed_id(self, client, feed_with_object_values):
        """Test filtering by feed ID."""
        feed = feed_with_object_values
        
        response = client.get(f'/api/v1/values/scos/?feed_id={feed.feed_id}')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return all SCOs from this feed
        assert data['total_results_count'] == 5
    
    def test_filter_by_stix_id(self, client, feed_with_object_values):
        """Test filtering by exact STIX object ID."""
        stix_id = "ipv4-addr--ba6b3f21-d818-4e7c-bfff-765805177512"
        
        response = client.get(f'/api/v1/values/scos/?id={stix_id}')
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['total_results_count'] == 1
        assert data['values'][0]['id'] == stix_id
    
    def test_sdo_types_not_returned(self, client, feed_with_object_values):
        """Test that SDO types are not returned in SCO endpoint."""
        response = client.get('/api/v1/values/scos/')
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify no SDO types in results
        sdo_types = ['attack-pattern', 'malware', 'vulnerability', 'location']
        for obj in data['values']:
            assert obj['type'] not in sdo_types
    
    def test_ordering_by_stix_id(self, client, feed_with_object_values):
        """Test ordering results by stix_id."""
        response = client.get('/api/v1/values/scos/?sort=stix_id_ascending')
        
        assert response.status_code == 200
        data = response.json()
        
        stix_ids = [obj['id'] for obj in data['values']]
        assert stix_ids == sorted(stix_ids)

    def test_pagination(self, client, feed_with_object_values):
        """Test pagination of results."""
        response = client.get('/api/v1/values/scos/?page_size=2')
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data['values']) == 2
        assert data['total_results_count'] == 5
    
    def test_no_ttp_type_in_sco_results(self, client, feed_with_object_values):
        """Test that SCOs don't have ttp_type field in results."""
        response = client.get('/api/v1/values/scos/')
        
        assert response.status_code == 200
        data = response.json()
        
        for obj in data['values']:
            # ttp_type should not be present (null fields are removed)
            assert "knowledgebase" not in obj


@pytest.mark.django_db
class TestSDOValueView:
    """Tests for the SDO (Domain Object) values endpoint."""

    @pytest.fixture(autouse=True)
    def default_sdo_objects(self):
        self.default_object_ids = {

        }
    
    def test_list_all_sdos(self, client, feed_with_object_values):
        """Test listing all SDO values."""
        response = client.get('/api/v1/values/sdos/')
        
        assert response.status_code == 200
        data = response.json()
        assert 'values' in data
        
        # Should return all unique SDO objects (4 unique)
        assert len({obj['id'] for obj in data['values']}) == len(data['values'])  # All unique
        assert data['total_results_count'] == 4
    
    def test_filter_by_type(self, client, feed_with_object_values):
        """Test filtering SDOs by type."""
        response = client.get('/api/v1/values/sdos/?types=attack-pattern')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return only attack-pattern (1 unique)
        assert data['total_results_count'] == 1
        assert data['values'][0]['type'] == 'attack-pattern'
    
    def test_filter_by_ttp_type(self, client, feed_with_object_values):
        """Test filtering by TTP type."""
        response = client.get('/api/v1/values/sdos/?knowledgebases=enterprise-attack')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return only enterprise-attack objects (1)
        assert data['total_results_count'] == 1
        assert data['values'][0]["knowledgebase"] == 'enterprise-attack'
    
    def test_filter_by_multiple_knowledgebases(self, client, feed_with_object_values):
        """Test filtering by multiple TTP types."""
        response = client.get('/api/v1/values/sdos/?knowledgebases=cve,location')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return CVE (1) + location (1) = 2 objects
        assert data['total_results_count'] == 2
        knowledgebases = [obj["knowledgebase"] for obj in data['values']]
        assert all(t in ['cve', 'location'] for t in knowledgebases)
    
    def test_filter_by_value_searches_name(self, client, feed_with_object_values):
        """Test that value filter searches name field using substring matching."""
        response = client.get('/api/v1/values/sdos/?value=WannaCry')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should find the WannaCry malware
        assert data['total_results_count'] == 1
        assert 'WannaCry' in data['values'][0]['values']['name']
    
    def test_filter_by_value_searches_aliases(self, client, feed_with_object_values):
        """Test that value filter searches aliases using substring matching."""
        response = client.get('/api/v1/values/sdos/?value=T1566.002')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should find the Spearphishing attack pattern
        assert data['total_results_count'] == 1
        assert data['values'][0]['type'] == 'attack-pattern'
    
    def test_filter_by_value_exact(self, client, feed_with_object_values):
        """Test value_exact matches exact individual values only."""
        response = client.get('/api/v1/values/sdos/?value=CVE-2021-44228&value_exact=true')
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['total_results_count'] == 1
        assert 'CVE-2021-44228' in data['values'][0]['values']['name']
    
    def test_filter_by_post_id(self, client, feed_with_object_values):
        """Test filtering by post ID."""

        # Get second post's ID
        feed = feed_with_object_values
        files = File.objects.filter(feed=feed).order_by('post__pubdate')
        second_file = files[1]
        post_id = second_file.post_id
        
        response = client.get(f'/api/v1/values/sdos/?post_id={post_id}')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return SDOs from second post (2: malware, location)
        assert data['total_results_count'] == 2
        
    
    def test_filter_by_feed_id(self, client, feed_with_object_values):
        """Test filtering by feed ID."""
        feed = feed_with_object_values
        
        response = client.get(f'/api/v1/values/sdos/?feed_id={feed.feed_id}')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return all SDOs from this feed
        assert data['total_results_count'] == 4
    
    def test_filter_by_stix_id(self, client, feed_with_object_values):
        """Test filtering by exact STIX object ID."""
        stix_id = "attack-pattern--0f4a0c76-ab2d-4cb0-85d3-3f0efb8cba4d"
        
        response = client.get(f'/api/v1/values/sdos/?id={stix_id}')
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['total_results_count'] == 1
        assert data['values'][0]['id'] == stix_id
    
    def test_sco_types_not_returned(self, client, feed_with_object_values):
        """Test that SCO types are not returned in SDO endpoint."""
        response = client.get('/api/v1/values/sdos/')
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify no SCO types in results
        sco_types = ['ipv4-addr', 'domain-name', 'url']
        for obj in data['values']:
            assert obj['type'] not in sco_types
    
    def test_ttp_type_present_when_applicable(self, client, feed_with_object_values):
        """Test that ttp_type is present when it exists."""
        response = client.get('/api/v1/values/sdos/?knowledgebases=cve')
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['total_results_count'] == 1
        assert "knowledgebase" in data['values'][0]
        assert data['values'][0]["knowledgebase"] == 'cve'
    
    def test_ordering_by_knowledgebase(self, client, feed_with_object_values):
        """Test ordering results by knowledgebase."""
        response = client.get('/api/v1/values/sdos/?sort=knowledgebase_ascending')
        
        assert response.status_code == 200
        data = response.json()
        
        # Extract knowledgebases, treating None as z string for sorting (None values should come last)
        knowledgebases = [obj.get("knowledgebase", 'z') or 'z' for obj in data['values']]
        assert knowledgebases == sorted(knowledgebases)

    def test_ordering_by_value_uses_first_key(self, client, feed_with_object_values):
        """Test value ordering uses the first key alphabetically from values JSON."""
        feed = feed_with_object_values
        files = File.objects.filter(feed=feed).order_by('post__pubdate')

        ObjectValue.objects.create(
            stix_id="vulnerability--11111111-1111-1111-1111-111111111111",
            type="vulnerability",
            knowledgebase="cve",
            values={"z_key": "cve-z", "a_key": "cve-a"},
            file=files[0],
            created=timezone.now(),
            modified=timezone.now(),
        )
        ObjectValue.objects.create(
            stix_id="vulnerability--22222222-2222-2222-2222-222222222222",
            type="vulnerability",
            knowledgebase="cve",
            values={"z_key": "cve-a", "a_key": "cve-z"},
            file=files[1],
            created=timezone.now(),
            modified=timezone.now(),
        )
        ObjectValue.objects.create(
            stix_id="attack-pattern--33333333-3333-3333-3333-333333333333",
            type="attack-pattern",
            knowledgebase=None,
            values={"a_key": "aaa.example", "z_key": "zzz.example"},
            file=files[1],
        )

        response = client.get('/api/v1/values/sdos/?types=vulnerability,attack-pattern&sort=value_ascending')

        assert response.status_code == 200
        data = response.json()

        normalized_values = [list(obj['values'].values())[0].lower() for obj in data['values']]
        assert len(normalized_values) >= 3
        assert normalized_values == sorted(normalized_values)
    
    def test_combined_filters(self, client, feed_with_object_values):
        """Test combining multiple filters."""
        response = client.get('/api/v1/values/sdos/?types=vulnerability&knowledgebases=cve')
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['total_results_count'] == 1
        obj = data['values'][0]
        assert obj['type'] == 'vulnerability'
        assert obj["knowledgebase"] == 'cve'
    
    def test_created_modified_timestamps(self, client, feed_with_object_values):
        """Test that created and modified timestamps are returned."""
        response = client.get('/api/v1/values/sdos/')
        
        assert response.status_code == 200
        data = response.json()
        
        for obj in data['values']:
            assert 'created' in obj
            assert 'modified' in obj


@pytest.mark.django_db
class TestValuesViewEdgeCases:
    """Tests for edge cases and error conditions."""
    
    def test_empty_database(self, client):
        """Test querying when no ObjectValue entries exist."""
        response = client.get('/api/v1/values/scos/')
        
        assert response.status_code == 200
        data = response.json()
        assert data['total_results_count'] == 0
        assert data['values'] == []
    
    def test_invalid_filter_values(self, client, feed_with_object_values):
        """Test that invalid filter values are handled gracefully."""

        # Invalid UUID format
        response = client.get('/api/v1/values/scos/?post_id=invalid-uuid')
        # Should return 200 with no results or handle gracefully
        assert response.status_code in [200, 400]
    
    def test_nonexistent_stix_id(self, client, feed_with_object_values):
        """Test querying for non-existent STIX ID."""
        response = client.get('/api/v1/values/scos/?id=ipv4-addr--00000000-0000-0000-0000-000000000000')
        
        assert response.status_code == 200
        data = response.json()
        assert data['total_results_count'] == 0
    
    def test_value_search_no_results(self, client, feed_with_object_values):
        """Test value search that returns no results."""
        response = client.get('/api/v1/values/scos/?value=nonexistent-value-12345')
        
        assert response.status_code == 200
        data = response.json()
        assert data['total_results_count'] == 0
    
    def test_multiple_filters_narrow_results(self, client, feed_with_object_values):
        """Test that multiple filters properly narrow results."""

        # Get a specific post ID
        feed = feed_with_object_values
        first_file = File.objects.filter(feed=feed).order_by('post__pubdate').first()
        post_id = first_file.post_id
        
        # Filter by type AND post_id
        response = client.get(f'/api/v1/values/scos/?types=ipv4-addr&post_id={post_id}')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return only IPv4 addresses from that specific post
        for obj in data['values']:
            assert obj['type'] == 'ipv4-addr'