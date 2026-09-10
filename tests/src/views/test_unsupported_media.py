import pytest

from tests.utils import Transport


WRITE_OPERATIONS_WITH_BODIES = [
    ("POST", "/api/v1/feeds/"),
    ("PATCH", "/api/v1/feeds/{feed_id}/"),
    ("PATCH", "/api/v1/feeds/{feed_id}/fetch/"),
    ("POST", "/api/v1/feeds/{feed_id}/posts/"),
    ("PATCH", "/api/v1/feeds/{feed_id}/posts/{post_id}/"),
    ("PATCH", "/api/v1/feeds/{feed_id}/posts/{post_id}/reindex/"),
    ("PATCH", "/api/v1/feeds/{feed_id}/posts/{post_id}/reprocess/"),
    ("PATCH", "/api/v1/feeds/{feed_id}/posts/reindex/"),
    ("PATCH", "/api/v1/feeds/{feed_id}/reindex-pdfs/"),
    ("PATCH", "/api/v1/feeds/{feed_id}/reprocess-posts/"),
    ("POST", "/api/v1/feeds/skeleton/"),
    (
        "POST",
        "/api/v1/objects/reports/{report_id}/remove_objects/",
    ),
    ("PATCH", "/api/v1/posts/{post_id}/"),
    ("PATCH", "/api/v1/posts/{post_id}/reindex/"),
    ("PATCH", "/api/v1/posts/{post_id}/reprocess/"),
    ("POST", "/api/v1/profiles/"),
    ("PATCH", "/api/v1/topics/build_clusters/"),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("method", "schema_path"), WRITE_OPERATIONS_WITH_BODIES)
def test_write_operations_document_unsupported_media_type(
    client, api_schema, feed_with_posts, method, schema_path
):
    request_path = schema_path.format(
        feed_id=feed_with_posts.pk,
        post_id="561ed102-7584-4b7d-a302-43d4bca5605b",
        report_id="report--00000000-0000-4000-8000-000000000001",
    )
    response = client.generic(
        method,
        request_path,
        data=b"unsupported",
        content_type="application/octet-stream",
    )

    assert response.status_code == 415
    api_schema[schema_path][method].validate_response(
        Transport.get_st_response(response)
    )
