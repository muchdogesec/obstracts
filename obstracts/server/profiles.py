from dogesec_commons.stixifier.serializers import ProfileSerializer
from dogesec_commons.stixifier.views import ProfileView as CommonsProfileView
from drf_spectacular.utils import extend_schema, extend_schema_view

from . import autoschema as api_schema


@extend_schema_view(
    create=extend_schema(
        responses={
            400: api_schema.DEFAULT_400_ERROR,
            201: ProfileSerializer,
            415: api_schema.DEFAULT_415_ERROR,
        }
    )
)
class ProfileView(CommonsProfileView):
    """Project schema additions for the shared profile endpoints."""

