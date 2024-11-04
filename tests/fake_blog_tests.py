import requests
import json

# Base URL for feeds
base_url = "http://localhost:8001/api/v1/feeds/"

# Feed ID and post IDs
feed_id = "2d6575b8-3d90-5479-bdfe-b980b753ec40"
post_ids = [
    "10775d6c-9b84-523e-9e24-3a588349633d", 
    "c6a5afcd-2341-5a57-b936-b9a67667f57e",
    "fc50dda4-1806-581c-ae0e-e25ded740652",
    "ad852cd1-2d74-59b1-9ab2-1dcb4d9c7b87",
    "97f98a9f-437a-5ac2-96ef-e9307f1534de",
    "df6cd9d5-8493-5908-a3a6-2ae9b38ecf28"
]

def print_full_request_details(response):
    # Print full details of the request (method, URL, headers, and body)
    prepared_request = response.request
    print(f"\n--- Full HTTP Request ---")
    print(f"{prepared_request.method} {prepared_request.url}")
    print(f"Headers: {prepared_request.headers}")
    if prepared_request.body:
        print(f"Body: {prepared_request.body}")
    print(f"-------------------------\n")

def check_post_images(feed_id, post_id, expected_results):
    # Construct the URL for the post's images endpoint
    images_url = f"{base_url}{feed_id}/posts/{post_id}/images/"
    print(f"Sending GET request to retrieve images for post ID: {post_id} in feed ID: {feed_id}...")

    # Send the GET request
    response = requests.get(images_url)
    print_full_request_details(response)

    # Print the response content
    print(f"Response status code: {response.status_code}")
    print("Response content:")
    actual_results = response.json()
    print(json.dumps(actual_results, indent=2))

    # Debug information: compare actual and expected results
    print(f"\nExpected Results for post {post_id}:")
    print(json.dumps(expected_results, indent=2))

    # Check if the response matches the expected result
    assert actual_results == expected_results, f"Mismatch for post ID: {post_id}"

if __name__ == "__main__":
    print("Starting tests for post images...")

    # Expected empty response for most posts
    empty_response = {
        "page_size": 50,
        "page_number": 1,
        "page_results_count": 0,
        "total_results_count": 0,
        "images": []
    }

    # Expected response for the post with images (df6cd9d5-8493-5908-a3a6-2ae9b38ecf28)
    post_df6cd9d5_images_response = {
        "page_size": 50,
        "page_number": 1,
        "page_results_count": 4,
        "total_results_count": 4,
        "images": [
            {
                "name": "0_image_0.png",
                "url": "http://localhost:8001/uploads/df6cd9d5-8493-5908-a3a6-2ae9b38ecf28/files/0_image_0.png"
            },
            {
                "name": "0_image_1.png",
                "url": "http://localhost:8001/uploads/df6cd9d5-8493-5908-a3a6-2ae9b38ecf28/files/0_image_1.png"
            },
            {
                "name": "0_image_2.png",
                "url": "http://localhost:8001/uploads/df6cd9d5-8493-5908-a3a6-2ae9b38ecf28/files/0_image_2.png"
            },
            {
                "name": "0_image_3.png",
                "url": "http://localhost:8001/uploads/df6cd9d5-8493-5908-a3a6-2ae9b38ecf28/files/0_image_3.png"
            }
        ]
    }

    # Expected response for post ID: 97f98a9f-437a-5ac2-96ef-e9307f1534de
    post_97f98a9f_images_response = {
        "page_size": 50,
        "page_number": 1,
        "page_results_count": 2,
        "total_results_count": 2,
        "images": [
            {
                "name": "0_image_0.png",
                "url": "http://localhost:8001/uploads/97f98a9f-437a-5ac2-96ef-e9307f1534de/files/0_image_0_Yyf06rf.png"
            },
            {
                "name": "0_image_1.png",
                "url": "http://localhost:8001/uploads/97f98a9f-437a-5ac2-96ef-e9307f1534de/files/0_image_1_N48kICR.png"
            }
        ]
    }

    # Loop through each post and run the tests
    for post_id in post_ids:
        if post_id == "df6cd9d5-8493-5908-a3a6-2ae9b38ecf28":
            # This post should return images
            check_post_images(feed_id, post_id, post_df6cd9d5_images_response)
        elif post_id == "97f98a9f-437a-5ac2-96ef-e9307f1534de":
            # This post should return two images
            check_post_images(feed_id, post_id, post_97f98a9f_images_response)
        else:
            # Other posts should return an empty result
            check_post_images(feed_id, post_id, empty_response)

    print("All tests completed successfully.")
