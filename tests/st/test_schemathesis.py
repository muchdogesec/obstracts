import time
from unittest.mock import patch
from urllib.parse import urlencode
import uuid
import schemathesis
import pytest
from schemathesis.core.transport import Response as SchemathesisResponse
from obstracts.wsgi import application as wsgi_app
from rest_framework.response import Response as DRFResponse
from hypothesis import settings
from hypothesis import strategies
from schemathesis.specs.openapi.checks import negative_data_rejection, positive_data_acceptance
from schemathesis.config import GenerationConfig

from tests.utils import Transport

schema = schemathesis.openapi.from_wsgi("/api/schema/?format=json", wsgi_app)
schema.config.base_url = "http://localhost:8001/"
schema.config.generation = GenerationConfig(allow_x00=False)

feed_ids = strategies.sampled_from([uuid.uuid4() for _ in range(3)]+["6ca6ce37-1c69-4a81-8490-89c91b57e557"])
post_ids = strategies.sampled_from([uuid.uuid4() for _ in range(3)]+["561ed102-7584-4b7d-a302-43d4bca5605b", "345c8d0b-c6ca-4419-b1f7-0daeb4e9278b", "72e1ad04-8ce9-413d-b620-fe7c75dc0a39", "42a5d042-26fa-41f3-8850-307be3f330cf"])
job_ids  = strategies.sampled_from([uuid.uuid4() for _ in range(3)]+["164716d9-85af-4a81-8f71-9168db3fadf0"])
profile_ids  = strategies.sampled_from([uuid.uuid4() for _ in range(3)]+["26fce5ea-c3df-45a2-8989-0225549c704b"])


@pytest.fixture(autouse=True)
def override_transport(monkeypatch, client):
    ## patch transport.get
    from schemathesis import transport
    monkeypatch.setattr(transport, "get", lambda _: Transport())



@pytest.fixture(autouse=True)
def db_setup(feed_with_posts, stixifier_profile, obstracts_job):
    from obstracts.cjob.celery import app
    app.conf.task_always_eager = False
    yield

@pytest.mark.django_db(transaction=True)
@schema.given(
    post_id=post_ids,
    feed_id=feed_ids,
    profile_id=profile_ids,
    job_id=job_ids
)
@schema.exclude(method=["POST", "PATCH"]).parametrize()
@settings(max_examples=30)
def test_api(case: schemathesis.Case, **kwargs):
    for k, v in kwargs.items():
        if k in case.path_parameters:
            case.path_parameters[k] = v
    case.call_and_validate(excluded_checks=[negative_data_rejection, positive_data_acceptance])


@pytest.mark.django_db(transaction=True)
@schema.given(
    post_id=post_ids,
    feed_id=feed_ids,
    profile_id=profile_ids,
    job_id=job_ids
)
@schema.include(method=["POST", "PATCH"]).parametrize()
@patch('celery.app.task.Task.run')
def test_imports(mock, case: schemathesis.Case, **kwargs):
    for k, v in kwargs.items():
        if k in case.path_parameters:
            case.path_parameters[k] = v
    case.call_and_validate(excluded_checks=[negative_data_rejection, positive_data_acceptance])
