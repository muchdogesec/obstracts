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
        
        total_results_count = data.get('total_results_count', 0)
        if total_results_count != 6:
            print(f"Test failed: total_results_count is {total_results_count}, expected 6.")
            return False

        posts = data.get('posts', [])
        print(f"Posts for feed ID: {feed_id}:")
        for post in posts:
            print(f"  Title: {post['title']}")

        return True
    else:
        print(f"Failed to retrieve posts for feed ID: {feed_id}. Status code: {response.status_code}")
        return False

def validate_feed_metadata(feed_id):
    """Validates that the required keys exist in the feed metadata."""
    metadata_url = f"{base_url}{feed_id}/"
    print(f"Sending GET request to retrieve metadata for feed ID: {feed_id}...")
    response = requests.get(metadata_url)
    print_full_request_details(response)
    
    if response.status_code == 200:
        metadata = response.json()
        required_keys = ["id", "count_of_posts", "title", "description", "url", 
                         "earliest_item_pubdate", "latest_item_pubdate", 
                         "datetime_added", "feed_type"]
        
        missing_keys = [key for key in required_keys if key not in metadata or not metadata[key]]
        
        if not missing_keys:
            print(f"Feed metadata for ID {feed_id} is complete and valid.")
        else:
            print(f"Feed metadata for ID {feed_id} is missing keys or values: {missing_keys}")
    else:
        print(f"Failed to retrieve metadata for feed ID: {feed_id}. Status code: {response.status_code}")

def check_post_images(feed_id, post_id):
    """Checks the images for a specific post and validates the total_results_count."""
    images_url = f"{base_url}{feed_id}/posts/{post_id}/images/"
    print(f"Sending GET request to retrieve images for post ID: {post_id} in feed ID: {feed_id}...")
    response = requests.get(images_url)
    print_full_request_details(response)

    if response.status_code == 200:
        data = response.json()
        total_results_count = data.get('total_results_count', 0)

        if total_results_count != 1:
            print(f"Test failed: total_results_count is {total_results_count}, expected 1.")
            return False

        print(f"Images for post ID: {post_id} are valid with total_results_count = 1.")
        return True
    else:
        print(f"Failed to retrieve images for post ID: {post_id}. Status code: {response.status_code}")
        return False

def check_post_markdown(feed_id, post_id):
    """Checks the markdown content for a specific post."""
    markdown_url = f"{base_url}{feed_id}/posts/{post_id}/markdown/"
    print(f"Sending GET request to retrieve markdown content for post ID: {post_id} in feed ID: {feed_id}...")
    response = requests.get(markdown_url)
    print_full_request_details(response)

    if response.status_code == 200:
        content = response.text
        if len(content.strip()) > 0:
            print(f"Markdown content for post ID: {post_id} is valid.")
            return True
        else:
            print(f"Test failed: Markdown content for post ID: {post_id} is empty.")
            return False
    else:
        print(f"Failed to retrieve markdown content for post ID: {post_id}. Status code: {response.status_code}")
        return False

if __name__ == "__main__":
    print("Starting feed deletion, creation, and verification script...")

    # Step 1: Define test blogs to add
    test_blogs = [
     # Basic threat intel extractions. AI relationship. Extract text from images.
        {
            "profile_id": "da4dddc2-86bd-52b7-8c09-37fc0f72b679",
            "url": "https://muchdogesec.github.io/fakeblog123/feeds/rss-feed-encoded.xml",
            "include_remote_blogs": False
        },
    # Basic threat intel extractions. Standard relationship. Extract text from images.
        {
            "profile_id": "bcf09ec5-d124-528a-bb21-480114231795",
            "url": "https://muchdogesec.github.io/fakeblog123/feeds/rss-feed-decoded.xml",
            "include_remote_blogs": False
        },
    # AI extractions. AI relationship. Extract text from images.
        {
            "profile_id": "a76c5353-a84b-552e-bbc4-ff6d0dc045e4",
            "url": "https://muchdogesec.github.io/fakeblog123/feeds/rss-feed-encoded-partial.xml",
            "include_remote_blogs": False
        },
    # External lookups. Standard relationship. Extract text from images.
        {
            "profile_id": "dba9d4b8-4b04-5794-96b7-56e74d6b08e1",
            "url": "https://muchdogesec.github.io/fakeblog123/feeds/rss-feed-decoded-partial.xml",
            "include_remote_blogs": False
        }
    ]

    # Step 2: Delete the specific feeds matching the blog URLs
    for blog in test_blogs:
        feed_id = generate_feed_id(blog["url"])
        print(f"Generated feed ID for deletion: {feed_id}")
        delete_feed(feed_id)

    # Step 3: Add new feeds, wait for job success, verify them, and check their posts
    for blog in test_blogs:
        feed_id, job_id = add_feed(blog["profile_id"], blog["url"], blog["include_remote_blogs"])
        if feed_id and job_id:
            job_success = wait_for_job_success(job_id)
            if job_success:
                check_feed(feed_id)
                get_posts_success = get_feed_posts(feed_id)
                if get_posts_success:
                    # Step 4: Validate the feed metadata after adding the feed
                    validate_feed_metadata(feed_id)
                    # Step 5: Check images for a specific post in the feed
                    images_check = check_post_images(feed_id, "84a8ff1c-c463-5a97-b0c4-93daf7102b5f")
                    if images_check:
                        # Step 6: Check markdown content for the same post
                        check_post_markdown(feed_id, "84a8ff1c-c463-5a97-b0c4-93daf7102b5f")
                    else:
                        print(f"Test failed for post ID 84a8ff1c-c463-5a97-b0c4-93daf7102b5f due to image validation failure.")
                        break
                else:
                    print(f"Test failed for feed ID {feed_id} due to incorrect total_results_count.")
                    break
            else:
                print(f"Job {job_id} failed. Terminating the test.")
                break  # Terminate script if any job fails

    print("Feed deletion, creation, and verification script completed.")
