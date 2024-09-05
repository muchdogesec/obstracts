import requests

# Base URL for feeds
base_url = "http://localhost:8001/api/v1/feeds/"

def get_feed_ids():
    print("Sending GET request to retrieve feeds...")
    response = requests.get(base_url)
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
        if response.status_code == 204:
            print(f"Successfully deleted feed with ID: {feed_id}")
        else:
            print(f"Failed to delete feed with ID: {feed_id}. Status code: {response.status_code}")

def add_feed(profile_id, url, include_remote_blogs):
    print("Sending POST request to add a new feed...")
    feed_data = {
        "profile_id": profile_id,
        "url": url,
        "include_remote_blogs": include_remote_blogs
    }
    response = requests.post(base_url, json=feed_data)
    if response.status_code == 201:
        print("Successfully added the new feed.")
    else:
        print(f"Failed to add the new feed. Status code: {response.status_code}")

if __name__ == "__main__":
    print("Starting feed deletion and creation script...")

    # Step 1: Get all feed IDs
    feed_ids = get_feed_ids()

    # Step 2: Delete each feed
    if feed_ids:
        delete_feeds(feed_ids)
    else:
        print("No feeds found to delete.")

    # Step 3: Add a new feed
    profile_id = "7e73c0b7-3ee1-54cf-86a7-8eaccd9392a2"
    url = "https://muchdogesec.github.io/fakeblog123/feeds/rss-feed-cdata-partial.xml"
    include_remote_blogs = False

    add_feed(profile_id, url, include_remote_blogs)

    print("Feed deletion and creation script completed.")
