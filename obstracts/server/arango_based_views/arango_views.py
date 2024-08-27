from .arango_helpers import ArangoDBHelper
from drf_spectacular.utils import extend_schema_view, extend_schema, OpenApiParameter
from rest_framework import viewsets, decorators, exceptions
import typing
from ..utils import Response

from django.conf import settings
if typing.TYPE_CHECKING:
    from obstracts import settings

class QueryParams:
    value = OpenApiParameter('value', description="search by value")
    types = OpenApiParameter('types', many=True, explode=False)
    post_id = OpenApiParameter('post_id', description="filter by post_id")
    SCO_PARAMS = [value, types, post_id]

    hide_processing_notes = OpenApiParameter('hide_processing_notes', type=bool, description="allows results to be filtered to remove Note objects")
    name = OpenApiParameter('name', description="allows results to be filtered on the name field. Is wildcard search.")
    labels = OpenApiParameter('labels', description="allows results to be filtered on the labels field. Is wildcard search.")

    SDO_PARAMS = [hide_processing_notes, name, labels]

    source_ref = OpenApiParameter('source_ref', description="filter SROs using `source_ref`")
    source_ref_type = OpenApiParameter('source_ref_type', description="filter source objects by type")
    target_ref = OpenApiParameter('target_ref', description="filter SROs using `target_ref`")
    target_ref_type = OpenApiParameter('target_ref_type', description="filter target objects by type")
    relationship_type = OpenApiParameter('relationship_type', description="filter by `relationship_type` field")

    SRO_PARAMS = [source_ref, source_ref_type, target_ref, target_ref_type, relationship_type]

@extend_schema_view(
    scos=extend_schema(
        summary="Get a STIX Cyber Observable Object",
        description="Search for STIX Cyber Observable Objects (aka Indicators of Compromise). If you have the object ID already, you can use the base GET Objects endpoint.",
    ),
    retrieve=extend_schema(
        summary="Get an object",
        description="Get an Object using its ID. You can search for Object IDs using the GET Objects SDO, SCO, or SRO endpoints."
    ),
    sdos=extend_schema(
        summary="Get a STIX Domain Object",
        description="Search for domain objects (aka TTPs). If you have the object ID already, you can use the base GET Objects endpoint.",
    ),
    sros=extend_schema(
        summary="Get a STIX Relationship Object",
        description="Search for relationship objects. This endpoint is particularly useful to search what Objects an SCO or SDO is linked to.",
    ),
)
class ObjectsView(viewsets.ViewSet):
    openapi_tags = ["Objects"]
    lookup_url_kwarg = "id"

    @extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters() + QueryParams.SCO_PARAMS,
    )
    @decorators.action(detail=False, methods=["GET"])
    def scos(self, request, *args, **kwargs):
        matcher = {}
        if post_id := request.query_params.dict().get('post_id'):
            matcher['_obstracts_post_id'] = post_id
        return ArangoDBHelper(settings.VIEW_NAME, request).get_scos(matcher=matcher)

    @extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters() + QueryParams.SDO_PARAMS,
    )
    @decorators.action(detail=False, methods=["GET"])
    def sdos(self, request, *args, **kwargs):
        return ArangoDBHelper(settings.VIEW_NAME, request).get_sdos()

    @extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters() + QueryParams.SRO_PARAMS,
    )
    @decorators.action(detail=False, methods=["GET"])
    def sros(self, request, *args, **kwargs):
        return ArangoDBHelper(settings.VIEW_NAME, request).get_sros()

    @extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters(),
    )
    def retrieve(self, request, *args, **kwargs):
        return ArangoDBHelper(settings.VIEW_NAME, request).get_objects_by_id(
            kwargs.get(self.lookup_url_kwarg)
        )


class ReportView(viewsets.ViewSet):
    openapi_tags = ["Objects"]
    lookup_url_kwarg = 'report_id'
    @extend_schema()
    def retrieve(self, request, *args, **kwargs):
        report_id = kwargs.get(self.lookup_url_kwarg)
        reports = ArangoDBHelper(settings.VIEW_NAME, request).get_report_by_id(
            report_id
        )
        if not reports:
            raise exceptions.NotFound(detail=f"report object with id `{report_id}` - not found")
        return Response(reports[-1])
    
    @extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters(),
    )
    def list(self, request, *args, **kwargs):
        return ArangoDBHelper(settings.VIEW_NAME, request).get_reports()
    
    @extend_schema(
            
    )
    def destroy(self, request, *args, **kwargs):
        report_id = kwargs.get(self.lookup_url_kwarg)
        ArangoDBHelper(settings.VIEW_NAME, request).remove_report(
            report_id
        )
        return Response()