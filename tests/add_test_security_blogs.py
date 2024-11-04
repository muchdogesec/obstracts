import requests
import time

# Base URL for feeds
base_url = "http://localhost:8001/api/v1/feeds/"

def print_full_request_details(response):
    # Print full details of the request (method, URL, headers, and body)
    prepared_request = response.request
    print(f"\n--- Full HTTP Request ---")
    print(f"{prepared_request.method} {prepared_request.url}")
    print(f"Headers: {prepared_request.headers}")
    if prepared_request.body:
        print(f"Body: {prepared_request.body}")
    print(f"-------------------------\n")

def get_feed_ids():
    print("Sending GET request to retrieve feeds...")
    response = requests.get(base_url)
    print_full_request_details(response)
    
    if response.status_code == 200:
        print("Successfully retrieved feeds.")
        data = response.json()
        feed_ids = [feed['id'] for feed in data.get('feeds', [])]
        print(f"Found {len(feed_ids)} feeds.")
        return feed_ids
    else:
        print(f"Failed to retrieve feeds. Status code: {response.status_code}")
        return []

def delete_feeds(feed_ids):
    for feed_id in feed_ids:
        delete_url = f"{base_url}{feed_id}/"
        print(f"Sending DELETE request for feed ID: {feed_id}...")
        response = requests.delete(delete_url)
        print_full_request_details(response)

        if response.status_code == 204:
            print(f"Successfully deleted feed with ID: {feed_id}")
        else:
            print(f"Failed to delete feed with ID: {feed_id}. Status code: {response.status_code}")

def add_feed(profile_id, url, include_remote_blogs):
    print(f"Sending POST request to add a new feed with URL: {url}...")
    feed_data = {
        "profile_id": profile_id,
        "url": url,
        "include_remote_blogs": include_remote_blogs
    }
    print("Request body:")
    print(feed_data)

    response = requests.post(base_url, json=feed_data)
    print_full_request_details(response)

    print(f"Response status code: {response.status_code}")
    print("Response headers:")
    print(response.headers)
    print("Response content:")
    print(response.text)

    if response.status_code in [200, 201]:
        feed_info = response.json()
        print(f"Successfully added the new feed with ID: {feed_info['feed_id']}")
        # Corrected: 'id' is the job ID, and 'feed_id' is the feed ID
        return feed_info['feed_id'], feed_info['id']
    else:
        print(f"Failed to add the new feed. Status code: {response.status_code}")
        return None, None

def wait_for_job_success(job_id, retries=10, delay=20):
    # Corrected the URL to query directly from the jobs endpoint
    job_url = f"http://localhost:8001/api/v1/jobs/{job_id}/"
    print(f"Checking job status for job ID: {job_id}...")

    for attempt in range(retries):
        print(f"API request being made: GET {job_url}")
        response = requests.get(job_url)
        print_full_request_details(response)
        
        if response.status_code == 200:
            job_info = response.json()
            state = job_info['state']
            print(f"Current job state: {state}")

            # Check if the job is no longer in the 'retrieving' state
            if state == "processed":
                print(f"Job {job_id} completed successfully.")
                return True
            elif state in ["processing_failed", "retrieve_failed"]:
                print(f"Job {job_id} failed with state: {state}")
                return False
            else:
                # The job is still retrieving or in another intermediate state, wait and retry
                print(f"Job {job_id} is still in progress. Retrying in {delay} seconds...")
                time.sleep(delay)  # Wait for 20 seconds before checking again
        else:
            print(f"Attempt {attempt + 1}/{retries} failed: Job ID {job_id} not ready yet. Status code: {response.status_code}. Retrying in {delay} seconds...")
            time.sleep(delay)
    
    print(f"Job {job_id} could not be retrieved after {retries} attempts.")
    return False

def check_feed(feed_id):
    check_url = f"{base_url}{feed_id}/"
    print(f"Sending GET request to check feed with ID: {feed_id}...")
    response = requests.get(check_url)
    print_full_request_details(response)
    
    if response.status_code == 200:
        print(f"Feed with ID: {feed_id} exists and is correct.")
    else:
        print(f"Failed to find feed with ID: {feed_id}. Status code: {response.status_code}")

def get_feed_posts(feed_id):
    posts_url = f"{base_url}{feed_id}/posts/"
    print(f"Sending GET request to retrieve posts for feed ID: {feed_id}...")
    response = requests.get(posts_url)
    print_full_request_details(response)

    if response.status_code == 200:
        print(f"Successfully retrieved posts for feed ID: {feed_id}.")
        data = response.json()
        posts = data.get('posts', [])
        if posts:
            print(f"Posts for feed ID: {feed_id}:")
            for post in posts:
                print(f"  ID: {post['id']} - Title: {post['title']}")
        else:
            print(f"No posts found for feed ID: {feed_id}.")
    else:
        print(f"Failed to retrieve posts for feed ID: {feed_id}. Status code: {response.status_code}")

if __name__ == "__main__":
    print("Starting feed deletion, creation, and verification script...")

    # Step 1: Get all feed IDs
    feed_ids = get_feed_ids()

    # Step 2: Delete each feed
    if feed_ids:
        delete_feeds(feed_ids)
    else:
        print("No feeds found to delete.")

    # Step 3: Define test blogs to add
    # these create feeds with IDs (in order)
    # b4e3f13c-0ad6-5abe-be01-2475d341bf84
    # 16341792-226e-5a55-829e-a7cbcd2d54af
    # ecfdd2cb-9727-52c9-bf18-9266b2e2fd61
    test_blogs = [
        {
            "profile_id": "7e73c0b7-3ee1-54cf-86a7-8eaccd9392a2",
            "url": "http://feeds.feedburner.com/Unit42",
            "include_remote_blogs": True
        },
        {
            "profile_id": "7e73c0b7-3ee1-54cf-86a7-8eaccd9392a2",
            "url": "https://unit42.paloaltonetworks.com/category/threat-research/feed/",
            "include_remote_blogs": False
        },
        {
          "profile_id": "7e73c0b7-3ee1-54cf-86a7-8eaccd9392a2",
          "url": "https://www.crowdstrike.com/en-us/blog/feed",
          "include_remote_blogs": False
        },
        # Additional test blogs can be added here as needed
    ]

    # Step 4: Add new feeds, wait for job success, verify them, and check their posts
    for blog in test_blogs:
        feed_id, job_id = add_feed(blog["profile_id"], blog["url"], blog["include_remote_blogs"])
        if feed_id and job_id:
            job_success = wait_for_job_success(job_id)
            if job_success:
                check_feed(feed_id)
                get_feed_posts(feed_id)

    print("Feed deletion, creation, and verification script completed.")
