from unittest.mock import patch
import uuid
import pytest
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

@pytest.mark.parametrize(
    "states,expected_ids",
    [
        (["in-queue"], {"9e0d79ed-94d9-42a3-aa41-4772ae922176"}),
        (["processing"], {"2583d09b-6535-4f15-9fd1-5dcb55230f08"}),
        (["in-queue", "processing"], {"9e0d79ed-94d9-42a3-aa41-4772ae922176", "2583d09b-6535-4f15-9fd1-5dcb55230f08"}),
        (["cancelled"], {"0014c5a1-7a5e-408f-88ea-83ec5a1b8af1"}),
        (["processed"], set()),
        ([], {"9e0d79ed-94d9-42a3-aa41-4772ae922176", "2583d09b-6535-4f15-9fd1-5dcb55230f08", "0014c5a1-7a5e-408f-88ea-83ec5a1b8af1"}),
    ]
)
@pytest.mark.django_db
def test_jobs_filter_by_multiple_states(client, api_schema, states, expected_ids):
    from obstracts.server import models as ob_models

    keep_1 = ob_models.Job.objects.create(
        id='9e0d79ed-94d9-42a3-aa41-4772ae922176',
        type=ob_models.JobType.FEED_INDEX,
        state=ob_models.JobState.QUEUED,
    )
    keep_2 = ob_models.Job.objects.create(
        id='2583d09b-6535-4f15-9fd1-5dcb55230f08',
        type=ob_models.JobType.PDF_INDEX,
        state=ob_models.JobState.PROCESSING,
    )
    ob_models.Job.objects.create(
        id='0014c5a1-7a5e-408f-88ea-83ec5a1b8af1',
        type=ob_models.JobType.REPROCESS_POSTS,
        state=ob_models.JobState.CANCELLED,
    )

    resp = client.get(
        f"/api/v1/jobs/?state={','.join(states)}"
    )
    assert resp.status_code == 200
    assert resp.data["total_results_count"] == len(expected_ids)

    returned = {item["id"] for item in resp.data["jobs"]}
    assert returned == expected_ids

    api_schema["/api/v1/jobs/"]["GET"].validate_response(Transport.get_st_response(resp))
