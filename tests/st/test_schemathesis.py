import time
import schemathesis
import pytest
from schemathesis.core.transport import Response as SchemathesisResponse
from obstracts.asgi import application as asgi_app
from obstracts.wsgi import application as wsgi_app
from rest_framework.response import Response as DRFResponse
from hypothesis import Phase, settings


schema = schemathesis.openapi.from_asgi("/api/schema/?format=json", asgi_app)
@pytest.mark.django_db
@schema.parametrize()
@settings(max_examples=10, phases=[Phase.explicit])
def test_api(case: schemathesis.Case):
    if case.method not in list(schema[case.path].keys()):
        return
    from django.test import Client
    client = Client()
    t = time.time()
    response: DRFResponse = client.generic(case.method, case.formatted_path, headers=case.headers, )
    elapsed = time.time() - t
    rr = SchemathesisResponse(response.status_code, headers={k: [v] for k, v in response.headers.items()}, content=response.content, request=response.wsgi_request, elapsed=elapsed, verify=True)
    schema[case.path][case.method].validate_response(rr)
