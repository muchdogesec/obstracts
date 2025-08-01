from tests.utils import Transport


def test_schema_view(client):
    resp = client.get('/api/schema/')
    assert resp.status_code == 200
    assert resp.headers['content-type'] == "application/vnd.oai.openapi; charset=utf-8"

def test_healthcheck(client):
    resp = client.get('/api/healthcheck/')
    assert resp.status_code == 204


def test_healthcheck_service(client, api_schema):
    resp = client.get('/api/healthcheck/service/')
    assert resp.status_code == 200
    api_schema['/api/healthcheck/service/']['GET'].validate_response(Transport.get_st_response(resp))
    