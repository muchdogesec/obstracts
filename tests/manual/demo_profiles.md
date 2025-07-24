## Minimum required body (pattern)

```json
    {
        "name": "Minimum required body (pattern)",
        "extractions": [
            "pattern_ipv4_address_only"
        ],
        "relationship_mode": "standard",
        "extract_text_from_image": false,
        "defang": true
    }
```

## Pattern

ID = `becfca33-a5bf-5eb8-a601-433d47c7ba71`

```json
    {
        "identity_id": "identity--1cdc8321-5e67-42de-b2bf-c9505a891492",
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
            "pattern_phone_number"
        ],
        "relationship_mode": "standard",
        "extract_text_from_image": false,
        "defang": true,
        "ignore_image_refs": true,
        "ignore_link_refs": true,
        "ignore_extraction_boundary": false,
        "ignore_embedded_relationships": false,
        "ignore_embedded_relationships_sro": false,
        "ignore_embedded_relationships_smo": false,
        "ai_content_check_provider": "openai:gpt-4o",
        "ai_extract_if_no_incidence": false,
        "ai_create_attack_flow": false,
        "ai_create_attack_navigator_layer": false,
        "generate_pdf": true
    }
```

## AI

ID = `555c01e1-bbeb-5b05-bfed-9f6f9156fdb3`

```json
    {
        "name": "AI 1",
        "extractions": [
            "ai_ipv4_address_only",
            "ai_domain_name_only",
            "ai_url",
            "ai_mitre_attack_enterprise"
        ],
        "ai_settings_extractions": ["openai:gpt-4o"],
        "relationship_mode": "ai",
        "ai_settings_relationships": "openai:gpt-4o",
        "extract_text_from_image": false,
        "defang": true,
        "ignore_image_refs": true,
        "ignore_link_refs": true,
        "ignore_extraction_boundary": false,
        "ignore_embedded_relationships": false,
        "ignore_embedded_relationships_sro": true,
        "ignore_embedded_relationships_smo": true,
        "ai_create_attack_flow": false,
        "ai_summary_provider": "openai:gpt-4o",
        "ai_content_check_provider": "openai:gpt-4o",
        "generate_pdf": true
    }
```