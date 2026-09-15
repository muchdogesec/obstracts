from typing import List
import uuid
from drf_spectacular.openapi import AutoSchema
from dogesec_commons.utils.autoschema import CustomAutoSchema
import uritemplate
from dogesec_commons.utils.serializers import CommonErrorSerializer as ErrorSerializer
from drf_spectacular.utils import OpenApiResponse, OpenApiExample, OpenApiParameter
from drf_spectacular.contrib.django_filters import DjangoFilterExtension, get_view_model

from rest_framework.views import exception_handler
from rest_framework.exceptions import ValidationError
from django.core import exceptions

class OverrideDjangoFilterExtension(DjangoFilterExtension):
    priority = 1
    def get_schema_operation_parameters(self, auto_schema, *args, **kwargs):
        model = get_view_model(auto_schema.view)
        if not model:
            return self.target.get_schema_operation_parameters(auto_schema.view, *args, **kwargs)
        return super().get_schema_operation_parameters(auto_schema, *args, **kwargs)


class ObstractsAutoSchema(CustomAutoSchema):
    url_path_params: list[OpenApiParameter] = [
        OpenApiParameter('feed_id', type=uuid.UUID, location=OpenApiParameter.PATH, description="You can search and retrieve a Feed ID for a blog using the Get Feeds endpoint. The value is always a UUIDv4, e.g. `16c1ec28-aee1-470d-84a2-a56314511e1c`"),
        OpenApiParameter('post_id', type=uuid.UUID, location=OpenApiParameter.PATH, description="You can search and retrieve a Post ID for a blog using the Get Posts for a Feed endpoint. The value is always a UUIDv4, e.g. `ad343f60-4432-4b0d-9cca-2c3069eeef14`"),
        OpenApiParameter('job_id', type=uuid.UUID, location=OpenApiParameter.PATH, description="You can search and retrieve a Job ID for a blog using the Get Jobs endpoint. The value is always a UUIDv4, e.g. `2ece3fa5-e04b-457b-97cf-aef6efba8580"),
        OpenApiParameter('object_id', type=str, location=OpenApiParameter.PATH, description="This is the STIX ID of an object, e.g. `threat-actor--dfaa8d77-07e2-4e28-b2c8-92e9f7b04428`, `ipv4-addr--3f604e4b-d889-4f8b-9e8e-93d34fb12f7a`. You can search and retrieve a STIX object ID using the Get Objects SDO/SCO/SRO endpoints."),
        OpenApiParameter('profile_id', type=str, location=OpenApiParameter.PATH, description="You can search and retrieve a Profile ID for a Profile you have created using the Get Profiles endpoint. The value is always a UUIDv4, e.g. `85c4d787-0906-4d3c-a580-be980c4ebf86"),
        OpenApiParameter('extractor_id', type=str, location=OpenApiParameter.PATH, description="You can search and retrieve an Extractor ID using the Get Extractors endpoint. An example ID is; `lookup_mitre_cwe`"),
        OpenApiParameter('report_id', type=str, location=OpenApiParameter.PATH, description="This is the STIX ID of a report object, e.g. `report--0c16301f-7b2f-45c7-b4c5-c35b464e9696`. You can search and retrieve a STIX Report object ID using the Get SDO objects endpoints."),
    ]
    def get_override_parameters(self):
        params = super().get_override_parameters()
        path_variables = uritemplate.variables(self.path)
        for param in self.url_path_params:
            if param.name in path_variables:
                params.append(param)
        return params
    
    def get_tags(self) -> List[str]:
        if hasattr(self.view, "openapi_tags"):
            return self.view.openapi_tags
        return super().get_tags()

    def _map_serializer(self, serializer, direction, bypass_extensions=False):
        if getattr(serializer, "get_schema", None):
            return serializer.get_schema()
        return super()._map_serializer(serializer, direction, bypass_extensions)
    

DEFAULT_400_ERROR = OpenApiResponse(
    ErrorSerializer,
    "The server did not understand the request",
    [
        OpenApiExample(
            "http400",
            {"message": " The server did not understand the request", "code": 400},
        )
    ],
)


DEFAULT_404_ERROR = OpenApiResponse(
    ErrorSerializer,
    "Resource not found",
    [
        OpenApiExample(
            "http404",
            {
                "message": "The server cannot find the resource you requested",
                "code": 404,
            },
        )
    ],
)
