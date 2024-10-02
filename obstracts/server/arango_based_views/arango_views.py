from .arango_helpers import OBJECT_TYPES, ArangoDBHelper, SCO_TYPES, SDO_TYPES, SMO_TYPES, SRO_SORT_FIELDS, SMO_SORT_FIELDS, SCO_SORT_FIELDS, SDO_SORT_FIELDS
from drf_spectacular.utils import extend_schema_view, extend_schema, OpenApiParameter
from rest_framework import viewsets, decorators, exceptions
import typing
from ..utils import Response

from django.conf import settings

if typing.TYPE_CHECKING:
    from obstracts import settings


class QueryParams:
    value = OpenApiParameter(
        "value",
        description="Search by the `value` field field of the SCO. This is the IoC. So if you're looking to retrieve a IP address by address you would enter the IP address here. Similarly, if you're looking for a credit card you would enter the card number here. \n\n Search is wildcard. For example, `1.1` will return SCOs with `value` fields; `1.1.1.1`, `2.1.1.2`, etc. \n\n If `value` field is named differently for the Object (e.g. `hash`) it will still be searched because these have been aliased to the `value` in the database search).",
    )
    sco_types = OpenApiParameter(
        "types",
        many=True,
        explode=False,
        description="Filter the results by one or more STIX SCO Object types",
        enum=SCO_TYPES,
    )
    post_id = OpenApiParameter(
        "post_id",
        description="Filter the results to only contain objects present in the specified Post ID. Get a Post ID using the Feeds endpoints.",
    )
    SCO_PARAMS = [value, sco_types, post_id, OpenApiParameter('sort', enum=SCO_SORT_FIELDS)]

    include_txt2stix_notes = OpenApiParameter(
        "include_txt2stix_notes",
        type=bool,
        default=False,
        description="txt2stix creates 3 STIX note Objects that provide information about the processing job. This data is only really helpful for debugging issues, but not for intelligence sharing. Setting this parameters value to `true` will include these STIX note Objects in the response. Most of the time you want to set this parameter to `false` (the default value).",
    )
    name = OpenApiParameter(
        "name",
        description="Allows results to be filtered on the `name` field of the SDO. Search is wildcard. For example, `Wanna` will return SDOs with the `name`; `WannaCry`, `WannaSmile`, etc.",
    )
    labels = OpenApiParameter(
        "labels",
        description="Allows results to be filtered on each value in the `labels` field of the SDO. Each value in the `labels` list will be searched individually. \n\n Search is wildcard. For example, `needs` will return SDOs with `labels`; `need-attribution`, `needs-review`, etc. The value entered only needs to match one item in the `labels` list to return results.",
    )
    sdo_types = OpenApiParameter(
        "types",
        many=True,
        explode=False,
        description="Filter the results by one or more STIX Domain Object types",
        enum=SDO_TYPES,
    )

    SDO_PARAMS = [include_txt2stix_notes, name, labels, sdo_types, OpenApiParameter('sort', enum=SDO_SORT_FIELDS)]

    source_ref = OpenApiParameter(
        "source_ref",
        description="Filter the results on the `source_ref` fields. The value entered should be a full ID of a STIX SDO or SCO which can be obtained from the respective Get Object endpoints. This endpoint allows for graph traversal use-cases as it returns STIX `relationship` objects that will tell you what objects are related to the one entered (in the `target_ref` property).",
    )
    source_ref_type = OpenApiParameter(
        "source_ref_type",
        many=True,
        explode=False,
        description="Filter the results by the STIX object type in the `source_ref` field. Unlike the `source_ref` filter that requires a full STIX object ID, this filter allows for a more open search. For example, `attack-pattern` will return all `relationship` Objects where the `source_ref` contains the ID of an `attack-pattern` Object.",
    )
    target_ref = OpenApiParameter(
        "target_ref",
        description="Filter the results on the `target_ref` fields. The value entered should be a full ID of a STIX SDO or SCO which can be obtained from the respective Get Object endpoints. This endpoint allows for graph traversal use-cases as it returns STIX `relationship` objects that will tell you what objects are related to the one entered (in the `source_ref` property).",
    )
    target_ref_type = OpenApiParameter(
        "target_ref_type",
        many=True,
        explode=False,
        description="Filter the results by the STIX object type in the `target_ref` field. Unlike the `target_ref` filter that requires a full STIX object ID, this filter allows for a more open search. For example, `attack-pattern` will return all `relationship` Objects where the `target_ref` contains the ID of an `attack-pattern` Object.",
    )
    relationship_type = OpenApiParameter(
        "relationship_type",
        description="Filter the results on the `relationship_type` field. Search is wildcard. For example, `in` will return `relationship` objects with ``relationship_type`s; `found-in`, `located-in`, etc.",
    )

    SRO_PARAMS = [
        source_ref,
        source_ref_type,
        target_ref,
        target_ref_type,
        relationship_type,
        include_txt2stix_notes,
        OpenApiParameter('sort', enum=SRO_SORT_FIELDS),
    ]

    types = OpenApiParameter(
        "types",
        many=True,
        explode=False,
        description="Filter the results by one or more STIX Object types",
        enum=OBJECT_TYPES,
    )
    OBJECTS_PARAMS = [
        include_txt2stix_notes,
        types,
    ]

    types = OpenApiParameter(
        "types",
        many=True,
        explode=False,
        description="Filter the results by one or more STIX Object types",
        enum=SMO_TYPES,
    )
    SMO_PARAMS = [
        types,
        OpenApiParameter('sort', enum=SMO_SORT_FIELDS),
    ]

    
class SingleObjectView(viewsets.ViewSet):
    lookup_url_kwarg = "object_id"
    openapi_tags = ["Objects"]

    @extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters(),
    )
    def retrieve(self, request, *args, **kwargs):
        return ArangoDBHelper(settings.VIEW_NAME, request).get_objects_by_id(
            kwargs.get(self.lookup_url_kwarg)
        )
    
class SingleObjectReportsView(SingleObjectView):
    @extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema('reports', {'type': 'string'}),
        parameters=ArangoDBHelper.get_schema_operation_parameters(),
    )
    @decorators.action(detail=True, methods=['GET'])
    def reports(self, request, *args, **kwargs):
        return ArangoDBHelper(settings.VIEW_NAME, request).get_containing_reports(kwargs.get(self.lookup_url_kwarg))
    
   
@extend_schema_view(
    retrieve=extend_schema(
        summary="Get a STIX Domain Object",
        description="Get a SDO by its ID",
    ),
    list=extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters()
        + QueryParams.SDO_PARAMS,
        summary="Get STIX Domain Objects",
        description="Search for domain objects (aka TTPs). If you have the object ID already, you can use the base GET Objects endpoint.",
    ),
    reports=extend_schema(
        summary="Get all Reports belonging to SDO ID",
        description="Using the SDO ID, you can find all reports the SDO is mentioned in",
    ),
)
class SDOView(SingleObjectReportsView):
    def list(self, request, *args, **kwargs):
        return ArangoDBHelper(settings.VIEW_NAME, request).get_sdos()
   
@extend_schema_view(
    retrieve=extend_schema(
        summary="Get a STIX Cyber Observable Object",
        description="Get an SCO by its ID",
    ),
    list=extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters()
        + QueryParams.SCO_PARAMS,
        summary="Get STIX Cyber Observable Objects",
        description="Search for STIX Cyber Observable Objects (aka Indicators of Compromise). If you have the object ID already, you can use the base GET Objects endpoint.",
    ),
    reports=extend_schema(
        summary="Get all Reports belonging to SCO ID",
        description="Using the SCO ID, you can find all reports the SCO is mentioned in",
    ),
)
class SCOView(SingleObjectReportsView):
    def list(self, request, *args, **kwargs):
        matcher = {}
        if post_id := request.query_params.dict().get("post_id"):
            matcher["_obstracts_post_id"] = post_id
        return ArangoDBHelper(settings.VIEW_NAME, request).get_scos(matcher=matcher)

   
@extend_schema_view(
    retrieve=extend_schema(
        summary="Get a STIX Meta Object",
        description="Get an SMO by its ID",
    ),
    list=extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters()
        + QueryParams.SMO_PARAMS,
        summary="Get STIX Meta Objects",
        description="Search for meta objects. If you have the object ID already, you can use the base GET Objects endpoint.",
    )
)
class SMOView(SingleObjectView):
    def list(self, request, *args, **kwargs):
        return ArangoDBHelper(settings.VIEW_NAME, request).get_smos()

   
@extend_schema_view(
    retrieve=extend_schema(
        summary="Get a STIX Relationship Object",
        description="Get an SRO by its ID",
    ),
    list=extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters()
        + QueryParams.SRO_PARAMS,
        ),
        summary="Get STIX Relationship Objects",
        description="Search for relationship objects. This endpoint is particularly useful to search what Objects an SCO or SDO is linked to.",
)
class SROView(SingleObjectView):
    pass





class ReportView(viewsets.ViewSet):
    openapi_tags = ["Objects"]
    lookup_url_kwarg = "report_id"

    @extend_schema()
    def retrieve(self, request, *args, **kwargs):
        report_id = kwargs.get(self.lookup_url_kwarg)
        reports = ArangoDBHelper(settings.VIEW_NAME, request).get_report_by_id(
            report_id
        )
        if not reports:
            raise exceptions.NotFound(
                detail=f"report object with id `{report_id}` - not found"
            )
        return Response(reports[-1])

    @extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters(),
    )
    def list(self, request, *args, **kwargs):
        return ArangoDBHelper(settings.VIEW_NAME, request).get_reports()

    @extend_schema()
    def destroy(self, request, *args, **kwargs):
        report_id = kwargs.get(self.lookup_url_kwarg)
        ArangoDBHelper(settings.VIEW_NAME, request).remove_report(report_id)
        return Response()
