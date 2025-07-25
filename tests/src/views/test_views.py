def test_schema_view(client):
    resp = client.get('/api/schema/')
    assert resp.status_code == 200
    assert resp.headers['content-type'] == "application/vnd.oai.openapi; charset=utf-8"

def test_healthcheck(client):
    resp = client.get('/api/healthcheck/')
    assert resp.status_code == 204
