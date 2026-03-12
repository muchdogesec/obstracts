"""
Tests for Object Values endpoints (SCO and SDO views).

These tests verify the functionality of the /api/v1/values/scos/ and /api/v1/values/sdos/
endpoints which provide efficient querying of STIX object values extracted from posts.
"""

import pytest
from django.utils import timezone
from obstracts.server.models import ObjectValue, File
from history4feed.app import models as h4f_models
from tests.conftest import make_feed
from rest_framework.test import APIClient
import uuid


@pytest.fixture
def feed_with_object_values(stixifier_profile):
    """Create a feed with posts that have ObjectValue entries."""
    feed = make_feed("6ca6ce37-1c69-4a81-8490-89c91b57e557", stixifier_profile)
    
    # Get the files created by make_feed
    files = File.objects.filter(feed=feed).order_by('post__pubdate')
    
    # Create ObjectValue entries for different STIX object types
    # SCO: IPv4 addresses
    ObjectValue.objects.create(
        stix_id="ipv4-addr--ba6b3f21-d818-4e7c-bfff-765805177512",
        type="ipv4-addr",
        ttp_type=None,
        values={"value": "192.168.1.1"},
        file=files[0],
    )
    
    ObjectValue.objects.create(
        stix_id="ipv4-addr--ba6b3f21-d818-4e7c-bfff-765805177512",
        type="ipv4-addr",
        ttp_type=None,
        values={"value": "192.168.1.1"},
        file=files[1],  # Same IP in different post
    )
    
    ObjectValue.objects.create(
        stix_id="ipv4-addr--cc7b4f32-e929-5c8d-cfff-876916288623",
        type="ipv4-addr",
        ttp_type=None,
        values={"value": "10.0.0.1"},
        file=files[0],
    )
    
    # SCO: Domain names
    ObjectValue.objects.create(
        stix_id="domain-name--dd8c5e43-fa3a-6d9e-dfff-987027399734",
        type="domain-name",
        ttp_type=None,
        values={"value": "malicious.example.com"},
        file=files[0],
    )
    
    ObjectValue.objects.create(
        stix_id="domain-name--ee9d6f54-gb4b-7e0f-efff-098138400845",
        type="domain-name",
        ttp_type=None,
        values={"value": "phishing.example.net"},
        file=files[1],
    )
    
    # SCO: URL
    ObjectValue.objects.create(
        stix_id="url--ff0e7g65-hc5c-8f1g-ffff-109249511956",
        type="url",
        ttp_type=None,
        values={"value": "https://malicious.example.com/payload.exe"},
        file=files[0],
    )
    
    # SDO: Attack Pattern
    ObjectValue.objects.create(
        stix_id="attack-pattern--0f4a0c76-ab2d-4cb0-85d3-3f0efb8cba4d",
        type="attack-pattern",
        ttp_type="enterprise-attack",
        values={"name": "Spearphishing Link", "aliases": ["T1566.002"]},
        file=files[0],
        created=timezone.now(),
        modified=timezone.now(),
    )
    
    ObjectValue.objects.create(
        stix_id="attack-pattern--0f4a0c76-ab2d-4cb0-85d3-3f0efb8cba4d",
        type="attack-pattern",
        ttp_type="enterprise-attack",
        values={"name": "Spearphishing Link", "aliases": ["T1566.002"]},
        file=files[2],  # Same attack pattern in different post
        created=timezone.now(),
        modified=timezone.now(),
    )
    
    # SDO: Malware
    ObjectValue.objects.create(
        stix_id="malware--1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
        type="malware",
        ttp_type=None,
        values={"name": "WannaCry", "x_mitre_aliases": ["WannaCryptor", "WCry"]},
        file=files[1],
        created=timezone.now(),
        modified=timezone.now(),
    )
    
    # SDO: Vulnerability
    ObjectValue.objects.create(
        stix_id="vulnerability--2b3c4d5e-6f7a-8b9c-0d1e-2f3a4b5c6d7e",
        type="vulnerability",
        ttp_type="cve",
        values={"name": "CVE-2021-44228"},
        file=files[0],
        created=timezone.now(),
        modified=timezone.now(),
    )
    
    # SDO: Location
    ObjectValue.objects.create(
        stix_id="location--3c4d5e6f-7a8b-9c0d-1e2f-3a4b5c6d7e8f",
        type="location",
        ttp_type="location",
        values={"name": "United States", "country": "US", "region": "northern-america"},
        file=files[1],
        created=timezone.now(),
        modified=timezone.now(),
    )
    
    return feed


@pytest.mark.django_db
class TestSCOValueView:
    """Tests for the SCO (Cyber Observable) values endpoint."""
    
    def test_list_all_scos(self, feed_with_object_values):
        """Test listing all SCO values."""
        client = APIClient()
        response = client.get('/api/v1/values/scos/')
        
        assert response.status_code == 200
        data = response.json()
        assert 'values' in data
        
        # Should return all unique SCO objects (5 unique IPs/domains/URLs)
        assert data['total_results_count'] == 5
        
        # Check that results are deduplicated by stix_id
        stix_ids = [obj['id'] for obj in data['values']]
        assert len(stix_ids) == len(set(stix_ids))  # All unique
    
    def test_filter_by_type(self, feed_with_object_values):
        """Test filtering SCOs by type."""
        client = APIClient()
        response = client.get('/api/v1/values/scos/?types=ipv4-addr')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return only IPv4 addresses (2 unique)
        assert data['total_results_count'] == 2
        for obj in data['values']:
            assert obj['type'] == 'ipv4-addr'
    
    def test_filter_by_multiple_types(self, feed_with_object_values):
        """Test filtering by multiple types."""
        client = APIClient()
        response = client.get('/api/v1/values/scos/?types=ipv4-addr,domain-name')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return IPv4 (2) + domain-name (2) = 4 objects
        assert data['total_results_count'] == 4
        types = [obj['type'] for obj in data['values']]
        assert all(t in ['ipv4-addr', 'domain-name'] for t in types)
    
    def test_filter_by_value_wildcard(self, feed_with_object_values):
        """Test default search uses trigram matching for flexible matching."""
        client = APIClient()
        response = client.get('/api/v1/values/scos/?value=192.168')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return the 192.168.1.1 IP using trigram matching
        assert data['total_results_count'] == 1
        assert data['values'][0]['values']['value'] == '192.168.1.1'
    
    def test_filter_by_value_exact(self, feed_with_object_values):
        """Test value_exact search finds values containing the term (without trigram flexibility)."""
        client = APIClient()
        response = client.get('/api/v1/values/scos/?value=192.168.1.1&value_exact=true')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return the IP containing 192.168.1.1
        assert data['total_results_count'] == 1
        assert data['values'][0]['values']['value'] == '192.168.1.1'
    
    def test_filter_by_value_exact_substring_match(self, feed_with_object_values):
        """Test that exact match finds values containing the search term."""
        client = APIClient()
        response = client.get('/api/v1/values/scos/?value=192.168&value_exact=true')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return the IP since '192.168' is contained in '192.168.1.1'
        assert data['total_results_count'] == 1
        assert '192.168' in data['values'][0]['values']['value']
    
    def test_filter_by_post_id(self, feed_with_object_values):
        """Test filtering by post ID."""
        client = APIClient()
        
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
        
        # Verify all returned objects have this post in matched_posts
        for obj in data['values']:
            assert str(post_id) in [str(p) for p in obj['matched_posts']]
    
    def test_filter_by_feed_id(self, feed_with_object_values):
        """Test filtering by feed ID."""
        client = APIClient()
        feed = feed_with_object_values
        
        response = client.get(f'/api/v1/values/scos/?feed_id={feed.feed_id}')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return all SCOs from this feed
        assert data['total_results_count'] == 5
    
    def test_filter_by_stix_id(self, feed_with_object_values):
        """Test filtering by exact STIX object ID."""
        client = APIClient()
        stix_id = "ipv4-addr--ba6b3f21-d818-4e7c-bfff-765805177512"
        
        response = client.get(f'/api/v1/values/scos/?id={stix_id}')
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['total_results_count'] == 1
        assert data['values'][0]['id'] == stix_id
    
    def test_matched_posts_aggregation(self, feed_with_object_values):
        """Test that matched_posts aggregates all posts containing the object."""
        client = APIClient()
        
        # Query for the IP that appears in 2 posts
        response = client.get('/api/v1/values/scos/?value=192.168.1.1&value_exact=true')
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['total_results_count'] == 1
        obj = data['values'][0]
        
        # Should have 2 posts in matched_posts
        assert len(obj['matched_posts']) == 2
    
    def test_sdo_types_not_returned(self, feed_with_object_values):
        """Test that SDO types are not returned in SCO endpoint."""
        client = APIClient()
        response = client.get('/api/v1/values/scos/')
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify no SDO types in results
        sdo_types = ['attack-pattern', 'malware', 'vulnerability', 'location']
        for obj in data['values']:
            assert obj['type'] not in sdo_types
    
    def test_ordering_by_stix_id(self, feed_with_object_values):
        """Test ordering results by stix_id."""
        client = APIClient()
        response = client.get('/api/v1/values/scos/?sort=stix_id_ascending')
        
        assert response.status_code == 200
        data = response.json()
        
        stix_ids = [obj['id'] for obj in data['values']]
        assert stix_ids == sorted(stix_ids)
    
    def test_pagination(self, feed_with_object_values):
        """Test pagination of results."""
        client = APIClient()
        response = client.get('/api/v1/values/scos/?page_size=2')
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data['values']) == 2
        assert data['total_results_count'] == 5
    
    def test_no_ttp_type_in_sco_results(self, feed_with_object_values):
        """Test that SCOs don't have ttp_type field in results."""
        client = APIClient()
        response = client.get('/api/v1/values/scos/')
        
        assert response.status_code == 200
        data = response.json()
        
        for obj in data['values']:
            # ttp_type should not be present (null fields are removed)
            assert 'ttp_type' not in obj


@pytest.mark.django_db
class TestSDOValueView:
    """Tests for the SDO (Domain Object) values endpoint."""

    @pytest.fixture(autouse=True)
    def default_sdo_objects(self):
        self.default_object_ids = {

        }
    
    def test_list_all_sdos(self, feed_with_object_values):
        """Test listing all SDO values."""
        client = APIClient()
        response = client.get('/api/v1/values/sdos/')
        
        assert response.status_code == 200
        data = response.json()
        assert 'values' in data
        
        # Should return all unique SDO objects (4 unique)
        assert len({obj['id'] for obj in data['values']}) == len(data['values'])  # All unique
        assert data['total_results_count'] == 4
    
    def test_filter_by_type(self, feed_with_object_values):
        """Test filtering SDOs by type."""
        client = APIClient()
        response = client.get('/api/v1/values/sdos/?types=attack-pattern')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return only attack-pattern (1 unique)
        assert data['total_results_count'] == 1
        assert data['values'][0]['type'] == 'attack-pattern'
    
    def test_filter_by_ttp_type(self, feed_with_object_values):
        """Test filtering by TTP type."""
        client = APIClient()
        response = client.get('/api/v1/values/sdos/?ttp_types=enterprise-attack')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return only enterprise-attack objects (1)
        assert data['total_results_count'] == 1
        assert data['values'][0]['ttp_type'] == 'enterprise-attack'
    
    def test_filter_by_multiple_ttp_types(self, feed_with_object_values):
        """Test filtering by multiple TTP types."""
        client = APIClient()
        response = client.get('/api/v1/values/sdos/?ttp_types=cve,location')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return CVE (1) + location (1) = 2 objects
        assert data['total_results_count'] == 2
        ttp_types = [obj['ttp_type'] for obj in data['values']]
        assert all(t in ['cve', 'location'] for t in ttp_types)
    
    def test_filter_by_value_searches_name(self, feed_with_object_values):
        """Test that value filter searches name field using trigram matching."""
        client = APIClient()
        response = client.get('/api/v1/values/sdos/?value=WannaCry')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should find the WannaCry malware
        assert data['total_results_count'] == 1
        assert 'WannaCry' in data['values'][0]['values']['name']
    
    def test_filter_by_value_searches_aliases(self, feed_with_object_values):
        """Test that value filter searches aliases using trigram matching."""
        client = APIClient()
        response = client.get('/api/v1/values/sdos/?value=T1566.002')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should find the Spearphishing attack pattern
        assert data['total_results_count'] == 1
        assert data['values'][0]['type'] == 'attack-pattern'
    
    def test_filter_by_value_exact(self, feed_with_object_values):
        """Test value_exact finds values containing the term."""
        client = APIClient()
        response = client.get('/api/v1/values/sdos/?value=CVE-2021-44228&value_exact=true')
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['total_results_count'] == 1
        assert 'CVE-2021-44228' in data['values'][0]['values']['name']
    
    def test_filter_by_post_id(self, feed_with_object_values):
        """Test filtering by post ID."""
        client = APIClient()
        
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
        
        # Verify all returned objects have this post in matched_posts
        for obj in data['values']:
            assert str(post_id) in [str(p) for p in obj['matched_posts']]
    
    def test_filter_by_feed_id(self, feed_with_object_values):
        """Test filtering by feed ID."""
        client = APIClient()
        feed = feed_with_object_values
        
        response = client.get(f'/api/v1/values/sdos/?feed_id={feed.feed_id}')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return all SDOs from this feed
        assert data['total_results_count'] == 4
    
    def test_filter_by_stix_id(self, feed_with_object_values):
        """Test filtering by exact STIX object ID."""
        client = APIClient()
        stix_id = "attack-pattern--0f4a0c76-ab2d-4cb0-85d3-3f0efb8cba4d"
        
        response = client.get(f'/api/v1/values/sdos/?id={stix_id}')
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['total_results_count'] == 1
        assert data['values'][0]['id'] == stix_id
    
    def test_matched_posts_aggregation(self, feed_with_object_values):
        """Test that matched_posts aggregates all posts containing the object."""
        client = APIClient()
        
        # Query for the attack pattern that appears in 2 posts
        response = client.get('/api/v1/values/sdos/?value=Spearphishing')
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['total_results_count'] == 1
        obj = data['values'][0]
        
        # Should have 2 posts in matched_posts
        assert len(obj['matched_posts']) == 2
    
    def test_sco_types_not_returned(self, feed_with_object_values):
        """Test that SCO types are not returned in SDO endpoint."""
        client = APIClient()
        response = client.get('/api/v1/values/sdos/')
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify no SCO types in results
        sco_types = ['ipv4-addr', 'domain-name', 'url']
        for obj in data['values']:
            assert obj['type'] not in sco_types
    
    def test_ttp_type_present_when_applicable(self, feed_with_object_values):
        """Test that ttp_type is present when it exists."""
        client = APIClient()
        response = client.get('/api/v1/values/sdos/?ttp_types=cve')
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['total_results_count'] == 1
        assert 'ttp_type' in data['values'][0]
        assert data['values'][0]['ttp_type'] == 'cve'
    
    def test_ordering_by_ttp_type(self, feed_with_object_values):
        """Test ordering results by ttp_type."""
        client = APIClient()
        response = client.get('/api/v1/values/sdos/?sort=ttp_type_ascending')
        
        assert response.status_code == 200
        data = response.json()
        
        # Extract ttp_types, treating None as z string for sorting (None values should come last)
        ttp_types = [obj.get('ttp_type', 'z') or 'z' for obj in data['values']]
        assert ttp_types == sorted(ttp_types)
    
    def test_combined_filters(self, feed_with_object_values):
        """Test combining multiple filters."""
        client = APIClient()
        response = client.get('/api/v1/values/sdos/?types=vulnerability&ttp_types=cve')
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['total_results_count'] == 1
        obj = data['values'][0]
        assert obj['type'] == 'vulnerability'
        assert obj['ttp_type'] == 'cve'
    
    def test_created_modified_timestamps(self, feed_with_object_values):
        """Test that created and modified timestamps are returned."""
        client = APIClient()
        response = client.get('/api/v1/values/sdos/')
        
        assert response.status_code == 200
        data = response.json()
        
        for obj in data['values']:
            assert 'created' in obj
            assert 'modified' in obj


@pytest.mark.django_db
class TestValuesViewEdgeCases:
    """Tests for edge cases and error conditions."""
    
    def test_empty_database(self):
        """Test querying when no ObjectValue entries exist."""
        client = APIClient()
        response = client.get('/api/v1/values/scos/')
        
        assert response.status_code == 200
        data = response.json()
        assert data['total_results_count'] == 0
        assert data['values'] == []
    
    def test_invalid_filter_values(self, feed_with_object_values):
        """Test that invalid filter values are handled gracefully."""
        client = APIClient()
        
        # Invalid UUID format
        response = client.get('/api/v1/values/scos/?post_id=invalid-uuid')
        # Should return 200 with no results or handle gracefully
        assert response.status_code in [200, 400]
    
    def test_nonexistent_stix_id(self, feed_with_object_values):
        """Test querying for non-existent STIX ID."""
        client = APIClient()
        response = client.get('/api/v1/values/scos/?id=ipv4-addr--00000000-0000-0000-0000-000000000000')
        
        assert response.status_code == 200
        data = response.json()
        assert data['total_results_count'] == 0
    
    def test_value_search_no_results(self, feed_with_object_values):
        """Test value search that returns no results."""
        client = APIClient()
        response = client.get('/api/v1/values/scos/?value=nonexistent-value-12345')
        
        assert response.status_code == 200
        data = response.json()
        assert data['total_results_count'] == 0
    
    def test_multiple_filters_narrow_results(self, feed_with_object_values):
        """Test that multiple filters properly narrow results."""
        client = APIClient()
        
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
            assert str(post_id) in [str(p) for p in obj['matched_posts']]
