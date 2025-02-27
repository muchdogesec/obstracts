import argparse
import requests
import time
import uuid

# Base URL for feeds
base_url = "http://localhost:8001/api/v1/feeds/"

# UUID namespace for history4feed
NAMESPACE_UUID = uuid.UUID("6c6e6448-04d4-42a3-9214-4f0f7d02694e")

def generate_feed_id(feed_url):
    """Generates the feed ID using UUID v5 based on the feed URL."""
    return str(uuid.uuid5(NAMESPACE_UUID, feed_url))

def print_full_request_details(response):
    # Print full details of the request (method, URL, headers, and body)
    prepared_request = response.request
    print(f"\n--- Full HTTP Request ---")
    print(f"{prepared_request.method} {prepared_request.url}")
    print(f"Headers: {prepared_request.headers}")
    if prepared_request.body:
        print(f"Body: {prepared_request.body}")
    print(f"-------------------------\n")

def delete_feed(feed_id):
    delete_url = f"{base_url}{feed_id}/"
    print(f"Sending DELETE request for feed ID: {feed_id}...")
    response = requests.delete(delete_url)
    print_full_request_details(response)

    if response.status_code == 204:
        print(f"Successfully deleted feed with ID: {feed_id}")
    else:
        print(f"Failed to delete feed with ID: {feed_id}. Status code: {response.status_code}")

def add_feed(profile_id, url, include_remote_blogs, blog_entry):
    print(f"Sending POST request to add a new feed with URL: {url}...")
    # Build feed data with optional fields
    feed_data = {
        "profile_id": profile_id,
        "url": url,
        "include_remote_blogs": include_remote_blogs,
    }
    # Add optional fields only if they are defined in the blog entry
    if "pretty_url" in blog_entry:
        feed_data["pretty_url"] = blog_entry["pretty_url"]
    if "title" in blog_entry:
        feed_data["title"] = blog_entry["title"]
    if "description" in blog_entry:
        feed_data["description"] = blog_entry["description"]

    print("Request body:")
    print(feed_data)

    response = requests.post(base_url, json=feed_data)
    print_full_request_details(response)

    if response.status_code in [200, 201]:
        feed_info = response.json()
        print(f"Successfully added the new feed with ID: {feed_info['feed_id']}")
        return feed_info['feed_id'], feed_info['id']
    else:
        print(f"Failed to add the new feed. Status code: {response.status_code}")
        return None, None

def wait_for_job_success(job_id, retries=10, delay=60):
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

            if state == "processed":
                print(f"Job {job_id} completed successfully.")
                return True
            elif state in ["processing_failed", "retrieve_failed"]:
                print(f"Job {job_id} failed with state: {state}. Test is failing.")
                return False  # Terminate test if job fails
            else:
                print(f"Job {job_id} is still in progress. Retrying in {delay} seconds...")
                time.sleep(delay)
        else:
            print(f"Attempt {attempt + 1}/{retries} failed: Job ID {job_id} not ready yet. Status code: {response.status_code}. Retrying in {delay} seconds...")
            time.sleep(delay)
    
    print(f"Job {job_id} could not be retrieved after {retries} attempts. Test is failing.")
    return False  # Fail the test if it doesn't succeed within retries

if __name__ == "__main__":
    # Define CLI arguments
    parser = argparse.ArgumentParser(description="Feed management script for fakeblog123.")
    parser.add_argument(
        "--url", 
        type=str, 
        help="Specify a single blog URL to process. If not provided, all blogs will be processed."
    )
    args = parser.parse_args()

    # Test blogs list
    test_blogs = [
    # ==== OUR BLOG -- RESULTS FIXED
        # all properties
        {
            "profile_id": "da4dddc2-86bd-52b7-8c09-37fc0f72b679",
            "url": "https://muchdogesec.github.io/fakeblog123/feeds/rss-feed-encoded.xml",
            "include_remote_blogs": False,
            "pretty_url": "https://muchdogesec.github.io/fakeblog123/feeds",
            "title": "custom title",
            "description": "custom description",
            "use_search_index": False
        },
        # min properties
        {
            "profile_id": "bcf09ec5-d124-528a-bb21-480114231795",
            "url": "https://muchdogesec.github.io/fakeblog123/feeds/rss-feed-decoded.xml",
            "include_remote_blogs": False
        },
        # more blogs feed linked to same content (but slightly different URLs) to duplicate extractions
        {
            "profile_id": "da4dddc2-86bd-52b7-8c09-37fc0f72b679",
            "url": "https://muchdogesec.github.io/fakeblog123/feeds/rss-feed-encoded-partial.xml",
            "include_remote_blogs": False
        },
        {
            "profile_id": "da4dddc2-86bd-52b7-8c09-37fc0f72b679",
            "url": "https://muchdogesec.github.io/fakeblog123/feeds/rss-feed-decoded-partial.xml",
            "include_remote_blogs": False
        },
    # ==== OUR BLOG -- RESULTS UNPREDICATABLE
        {
            "profile_id": "da4dddc2-86bd-52b7-8c09-37fc0f72b679",
            "url": "https://blog.eclecticiq.com/",
            "include_remote_blogs": False,
            "title": "EclecticIQ Blog",
            "description": "A threat intel focused blog",
            "use_search_index": True
        },
        {
            "profile_id": "da4dddc2-86bd-52b7-8c09-37fc0f72b679",
            "url": "https://unit42.paloaltonetworks.com/category/threat-research/feed/",
            "include_remote_blogs": True,
            "title": "Unit42",
            "description": "A another search index blog",
            "use_search_index": True
        },
        # 16341792-226e-5a55-829e-a7cbcd2d54af
        {
            "profile_id": "da4dddc2-86bd-52b7-8c09-37fc0f72b679",
            "url": "https://www.crowdstrike.com/en-us/blog/feed",
            "include_remote_blogs": False
        },
        # examples of where include remote blogs needs to be true
        {
            "profile_id": "da4dddc2-86bd-52b7-8c09-37fc0f72b679",
            "url": "http://feeds.feedburner.com/Unit42",
            "pretty_url": "https://unit42.paloaltonetworks.com/",
            "include_remote_blogs": True,
            "title": "PAN Unit42 Blog",
            "description": "From feedburner"
        }
    ]

    # Filter blogs if a URL is provided
    if args.url:
        test_blogs = [blog for blog in test_blogs if blog["url"] == args.url]
        if not test_blogs:
            print(f"No matching blog found for URL: {args.url}")
            exit(1)

    print(f"Processing {len(test_blogs)} blog(s)...")

    # Process each blog
    for blog in test_blogs:
        feed_id = generate_feed_id(blog["url"])
        delete_feed(feed_id)
        feed_id, job_id = add_feed(blog["profile_id"], blog["url"], blog["include_remote_blogs"], blog)
        if feed_id and job_id:
            if not wait_for_job_success(job_id):
                print("Job failed. Exiting script.")
                exit(1)


    print("Feed processing completed.")
