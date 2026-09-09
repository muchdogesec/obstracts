import pytest

from tests.utils import Transport


@pytest.mark.django_db
def test_create_rejects_unsupported_media_type(client, api_schema):
    resp = client.post(
        "/api/v1/profiles/",
        data=b"unsupported",
        content_type="application/octet-stream",
    )

    assert resp.status_code == 415
    api_schema["/api/v1/profiles/"]["POST"].validate_response(
        Transport.get_st_response(resp)
    )
