from dogesec_commons.objects.views import (
    DELETE_OBJECTS_RESPONSE,
    ObjectsWithReportsView as CommonsObjectsWithReportsView,
)
from drf_spectacular.utils import extend_schema, extend_schema_view

from . import autoschema as api_schema


@extend_schema_view(
    delete_multi=extend_schema(
        responses={
            200: DELETE_OBJECTS_RESPONSE,
            415: api_schema.DEFAULT_415_ERROR,
        }
    )
)
class ObjectsWithReportsView(CommonsObjectsWithReportsView):
    """Project schema additions for the shared object endpoints."""

