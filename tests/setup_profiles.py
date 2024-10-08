import requests
import uuid

# Base URL
base_url = "http://localhost:8001/api/v1/profiles/"

# UUIDv5 namespace
namespace_uuid = uuid.UUID("a1f2e3ed-6241-5f05-ac2e-3394213b8e08")

def get_profile_ids():
    print("Sending GET request to retrieve profiles...")
    response = requests.get(base_url)
    if response.status_code == 200:
        print("Successfully retrieved profiles.")
        data = response.json()
        profile_ids = [profile['id'] for profile in data.get('profiles', [])]
        print(f"Found {len(profile_ids)} profiles.")
        return profile_ids
    else:
        print(f"Failed to retrieve profiles. Status code: {response.status_code}")
        return []

def delete_profiles(profile_ids):
    for profile_id in profile_ids:
        delete_url = f"{base_url}{profile_id}/"
        print(f"Sending DELETE request for profile ID: {profile_id}...")
        response = requests.delete(delete_url)
        if response.status_code == 204:
            print(f"Successfully deleted profile with ID: {profile_id}")
        else:
            print(f"Failed to delete profile with ID: {profile_id}. Status code: {response.status_code}")

def create_profiles(profiles):
    for profile in profiles:
        print(f"Sending POST request to create profile: {profile['name']}...")
        response = requests.post(base_url, json=profile)
        if response.status_code == 201:
            print(f"Successfully created profile: {profile['name']}")
        else:
            print(f"Failed to create profile: {profile['name']}. Status code: {response.status_code}")

def check_profiles(profiles):
    for profile in profiles:
        # Generate the UUIDv5 for the profile name
        profile_id = str(uuid.uuid5(namespace_uuid, profile['name']))
        check_url = f"{base_url}{profile_id}/"
        print(f"Sending GET request to check profile with ID: {profile_id}...")
        response = requests.get(check_url)
        if response.status_code == 200:
            print(f"Profile with ID: {profile_id} exists and is correct.")
        else:
            print(f"Failed to find profile with ID: {profile_id}. Status code: {response.status_code}")

if __name__ == "__main__":
    print("Starting profile deletion, creation, and verification script...")

    # Step 1: Get all profile IDs
    profile_ids = get_profile_ids()

    # Step 2: Delete each profile
    if profile_ids:
        delete_profiles(profile_ids)
    else:
        print("No profiles found to delete.")

    # Step 3: Create new profiles
    profiles = [
        #7e73c0b7-3ee1-54cf-86a7-8eaccd9392a2
        {
            "name": "Basic threat intel extractions. Standard relationship. Do not extract text from images.",
            "extractions": [
                "pattern_ipv4_address_only",
                "pattern_ipv6_address_only",
                "pattern_domain_name_only",
                "pattern_domain_name_subdomain",
                "pattern_url",
                "pattern_url_file",
                "pattern_host_name",
                "pattern_host_name_subdomain",
                "pattern_directory_windows",
                "pattern_directory_unix",
                "pattern_file_hash_md5",
                "pattern_file_hash_sha_1",
                "pattern_file_hash_sha_256",
                "pattern_file_hash_sha_512",
                "pattern_email_address",
                "pattern_mac_address",
                "pattern_windows_registry_key",
                "pattern_autonomous_system_number",
                "pattern_cryptocurrency_btc_wallet",
                "pattern_bank_card_mastercard",
                "pattern_bank_card_visa",
                "pattern_cve_id"
            ],
            "relationship_mode": "standard",
            "extract_text_from_image": False,
            "defang": True
        },
        #da4dddc2-86bd-52b7-8c09-37fc0f72b679
        {
            "name": "Basic threat intel extractions. Standard relationship. Extract text from images.",
            "extractions": [
                "pattern_ipv4_address_only",
                "pattern_ipv6_address_only",
                "pattern_domain_name_only",
                "pattern_domain_name_subdomain",
                "pattern_url",
                "pattern_url_file",
                "pattern_host_name",
                "pattern_host_name_subdomain",
                "pattern_directory_windows",
                "pattern_directory_unix",
                "pattern_file_hash_md5",
                "pattern_file_hash_sha_1",
                "pattern_file_hash_sha_256",
                "pattern_file_hash_sha_512",
                "pattern_email_address",
                "pattern_mac_address",
                "pattern_windows_registry_key",
                "pattern_autonomous_system_number",
                "pattern_cryptocurrency_btc_wallet",
                "pattern_bank_card_mastercard",
                "pattern_bank_card_visa",
                "pattern_cve_id"
            ],
            "relationship_mode": "standard",
            "extract_text_from_image": True,
            "defang": True
        }
    ]

    create_profiles(profiles)

    # Step 4: Check if profiles were created correctly
    check_profiles(profiles)

    print("Profile deletion, creation, and verification script completed.")
