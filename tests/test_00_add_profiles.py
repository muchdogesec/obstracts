import os
import time
from types import SimpleNamespace
import unittest, pytest
from urllib.parse import urljoin

import requests

from tests.utils import remove_unknown_keys, wait_for_jobs

base_url = os.environ["SERVICE_BASE_URL"]


DATA = [
    {
        "id": "982c5445-9ff8-513b-919b-b354127830c9",
        "name": "Pattern Only",
        "extractions": [
            "pattern_ipv4_address_only",
            "pattern_ipv4_address_port",
            "pattern_ipv4_address_cidr",
            "pattern_ipv6_address_only",
            "pattern_ipv6_address_port",
            "pattern_ipv6_address_cidr",
            "pattern_domain_name_only",
            "pattern_domain_name_subdomain",
            "pattern_url",
            "pattern_url_file",
            "pattern_host_name",
            "pattern_url_path",
            "pattern_host_name",
            "pattern_host_name_subdomain",
            "pattern_host_name_url",
            "pattern_host_name_file",
            "pattern_host_name_path",
            "pattern_file_name",
            "pattern_directory_windows",
            "pattern_directory_windows_with_file",
            "pattern_directory_unix",
            "pattern_directory_unix_file",
            "pattern_file_hash_md5",
            "pattern_file_hash_sha_1",
            "pattern_file_hash_sha_256",
            "pattern_file_hash_sha_512",
            "pattern_email_address",
            "pattern_mac_address",
            "pattern_windows_registry_key",
            "pattern_user_agent",
            "pattern_autonomous_system_number",
            "pattern_iban_number",
            "pattern_phone_number",
        ],
        "relationship_mode": "standard",
        "extract_text_from_image": False,
        "defang": True,
        "ignore_image_refs": True,
        "ignore_link_refs": True,
        "ai_summary_provider": None,
        "ignore_extraction_boundary": False,
        "ignore_embedded_relationships": False,
        "ignore_embedded_relationships_sro": False,
        "ignore_embedded_relationships_smo": False,
        "ai_content_check_provider": None,
        "ai_create_attack_flow": False,
    },
    {
        "id": "cbe66e30-c883-519a-a2bf-26aaaf17ae52",
        "name": "External lookups",
        "extractions": [
            "pattern_cryptocurrency_btc_wallet",
            "pattern_cryptocurrency_btc_transaction",
            "pattern_cve_id",
            "pattern_cpe_uri",
            "pattern_bank_card_mastercard",
            "pattern_bank_card_visa",
            "pattern_bank_card_amex",
            "pattern_bank_card_union_pay",
            "pattern_bank_card_diners",
            "pattern_bank_card_jcb",
            "pattern_bank_card_discover",
            "lookup_mitre_attack_enterprise_id",
            "lookup_mitre_attack_mobile_id",
            "lookup_mitre_attack_ics_id",
            "lookup_mitre_capec_id",
            "lookup_mitre_cwe_id",
            "lookup_mitre_atlas_id",
            "lookup_country_alpha2",
        ],
        "relationship_mode": "standard",
        "extract_text_from_image": False,
        "defang": True,
        "ignore_image_refs": True,
        "ignore_link_refs": True,
        "ai_summary_provider": None,
        "ignore_extraction_boundary": False,
        "ignore_embedded_relationships": False,
        "ignore_embedded_relationships_sro": False,
        "ignore_embedded_relationships_smo": False,
        "ai_content_check_provider": None,
        "ai_create_attack_flow": False,
    },
]


if model := os.getenv("TEST_AI_PROFILE_MODEL"):
    DATA.append(
        {
            "id": "57880900-5dc8-5e70-a900-b14aeb50a254",
            "name": "Pattern+ContentCheck",
            "extractions": [
                "pattern_ipv4_address_only",
                "pattern_ipv4_address_port",
                "pattern_ipv4_address_cidr",
                "pattern_ipv6_address_only",
                "pattern_ipv6_address_port",
                "pattern_ipv6_address_cidr",
                "pattern_domain_name_only",
                "pattern_domain_name_subdomain",
                "pattern_url",
                "pattern_url_file",
                "pattern_host_name",
                "pattern_url_path",
                "pattern_host_name",
                "pattern_host_name_subdomain",
                "pattern_host_name_url",
                "pattern_host_name_file",
                "pattern_host_name_path",
                "pattern_file_name",
                "pattern_directory_windows",
                "pattern_directory_windows_with_file",
                "pattern_directory_unix",
                "pattern_directory_unix_file",
                "pattern_file_hash_md5",
                "pattern_file_hash_sha_1",
                "pattern_file_hash_sha_256",
                "pattern_file_hash_sha_512",
                "pattern_email_address",
                "pattern_mac_address",
                "pattern_windows_registry_key",
                "pattern_user_agent",
                "pattern_autonomous_system_number",
                "pattern_iban_number",
                "pattern_phone_number",
            ],
            "relationship_mode": "standard",
            "extract_text_from_image": False,
            "defang": False,
            "ignore_image_refs": True,
            "ignore_link_refs": True,
            "ai_summary_provider": model,
            "ignore_extraction_boundary": False,
            "ignore_embedded_relationships": False,
            "ignore_embedded_relationships_sro": False,
            "ignore_embedded_relationships_smo": False,
            "ai_content_check_provider": model,
            "ai_create_attack_flow": False,
        }
    )


def all_profile_parameters():
    return [pytest.param(k["name"], k, k.get("should_fail", False)) for k in DATA]


@pytest.mark.parametrize(
    ["name", "profile", "should_fail"],
    all_profile_parameters(),
)
def test_add_profile(name, profile, should_fail):
    payload = profile
    endpoint = urljoin(base_url, "api/v1/profiles/")
    create_resp = requests.post(endpoint, json=payload)

    if should_fail:
        assert not create_resp.ok, "add feed request expected to fail"
        return

    assert create_resp.status_code == 201, f"create profile failed: {create_resp.text}"
    data = create_resp.json()
    for k in data:
        if k in profile:
            assert data[k] == profile[k]
