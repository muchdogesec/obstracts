from unittest.mock import patch
import uuid
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
    

def test_update_vulnerabilities_action(client, monkeypatch, db, celery_always_eager):
    from obstracts.server import models as ob_models    

    with patch('obstracts.cjob.tasks.update_vulnerabilities.run') as mock_update_vulnerabilities:
        resp = client.patch('/api/v1/tasks/sync-vulnerabilities/')
        assert resp.status_code == 201
        # job id returned in response
        data = resp.json()
        job_id = data.get('id')
        assert job_id
        # job exists with correct type
        job = ob_models.Job.objects.get(pk=job_id)
        assert job.type == ob_models.JobType.SYNC_VULNERABILITIES
        assert job.state == ob_models.JobState.PROCESSING
        mock_update_vulnerabilities.assert_called_once_with(uuid.UUID(job_id)) 
