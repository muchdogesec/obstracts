from typing import List, Literal
import uuid
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.plumbing import ResolvedComponent
from rest_framework.serializers import Serializer
import uritemplate
from .serializers import ErrorSerializer
from drf_spectacular.utils import OpenApiResponse, OpenApiExample, OpenApiParameter
from drf_spectacular.contrib.django_filters import DjangoFilterExtension, get_view_model, get_manager



class OverrideDjangoFilterExtension(DjangoFilterExtension):
    priority = 1
    def get_schema_operation_parameters(self, auto_schema, *args, **kwargs):
        model = get_view_model(auto_schema.view)
        if not model:
            return self.target.get_schema_operation_parameters(auto_schema.view, *args, **kwargs)
        return super().get_schema_operation_parameters(auto_schema, *args, **kwargs)


class ObstractsAutoSchema(AutoSchema):
    url_path_params: list[OpenApiParameter] = [
        OpenApiParameter('feed_id', type=uuid.UUID, location=OpenApiParameter.PATH, description="You can search and retrieve a Feed ID for a blog using the Get Feeds endpoint."),
        OpenApiParameter('post_id', type=uuid.UUID, location=OpenApiParameter.PATH, description="You can search and retrieve a Post ID for a blog using the Get Posts for a Feed endpoint."),
        OpenApiParameter('job_id', type=uuid.UUID, location=OpenApiParameter.PATH, description="You can search and retrieve a Job ID for a blog using the Get Jobs endpoint."),
        OpenApiParameter('object_id', type=str, location=OpenApiParameter.PATH, description="This is the STIX ID of an objects, e.g. `threat-actor--dfaa8d77-07e2-4e28-b2c8-92e9f7b04428`. You can search and retrieve a STIX object ID using the Get Objects SDO/SCO/SRO endpoints."),
        OpenApiParameter('profile_id', type=str, location=OpenApiParameter.PATH, description="You can search and retrieve a Profile ID for a Profile you have created using the Get Profiles endpoint."),
        OpenApiParameter('extractor_id', type=str, location=OpenApiParameter.PATH, description="You can search and retrieve an Alias ID using the Get Aliases endpoint. An example ID is; `country_name_to_iso2`"),
        OpenApiParameter('whitelist_id', type=str, location=OpenApiParameter.PATH, description="You can search and retrieve a Whitelist ID using the Get Whitelists endpoint. An example ID is; `alexa_top_1000_domains`"),
        OpenApiParameter('alias_id', type=str, location=OpenApiParameter.PATH, description="You can search and retrieve an Extractor ID using the Get Extractor endpoint. An example ID is; `pattern_ipv4_address_only`"),
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
