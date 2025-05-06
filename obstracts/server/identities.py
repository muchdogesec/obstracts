import logging
import textwrap
from rest_framework import viewsets, status, response


from drf_spectacular.utils import OpenApiParameter

import typing
from django.conf import settings

from dogesec_commons.objects.helpers import ArangoDBHelper

if typing.TYPE_CHECKING:
    from obstracts import settings
from .models import FeedProfile

from drf_spectacular.utils import extend_schema, extend_schema_view



@extend_schema_view(
    destroy=extend_schema(
        summary="Delete all objects associated with identity",
        description=textwrap.dedent(
            """
            This endpoint will delete all Files, Reports, Rules and any other STIX objects created using this identity. It will also delete the Identity object selected.
            """
        ),
    ),
    list=extend_schema(
        summary="Search identity objects",
        description=textwrap.dedent(
            """
            When a new feed is added, a STIX Identity object is created to represent it.

            That Identity ID is then used for all objects `created_by_ref` property for all STIX Objects belonging to that Feed.

            This endpoint will allow you to search for all the Identities that exist.
            """
        ),
    ),
    retrieve=extend_schema(
        summary="GET identity object by STIX ID",
        description=textwrap.dedent(
            """
            This endpoint will allow you to GET an Identity object by its STIX ID.
            """
        ),
    ),
)
class IdentityView(viewsets.ViewSet):
    
    SORT_PROPERTIES = [
        "created_descending",
        "created_ascending",
        "name_descending",
        "name_ascending",
    ]
    
    openapi_tags = ["Identities"]
    skip_list_view = True
    lookup_url_kwarg = "identity_id"
    lookup_value_regex = r'identity--[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
    openapi_path_params = [
        OpenApiParameter(
            lookup_url_kwarg, location=OpenApiParameter.PATH, type=dict(pattern=lookup_value_regex),
            description="The full STIX `id` of the Identity object. e.g. `identity--cfc24d7a-0b5e-4068-8bfc-10b66059afe0`."
        )
    ]

    @extend_schema(
        responses=ArangoDBHelper.get_paginated_response_schema(),
        parameters=ArangoDBHelper.get_schema_operation_parameters() + [
            OpenApiParameter('name', description="Filter by the `name` of identity object. Search is wildcard so `co` will match `company`, `cointel`, etc."),
            OpenApiParameter('sort', description="Sort the results by selected property", enum=SORT_PROPERTIES),
        ],
    )
    def list(self, request, *args, **kwargs):
        helper = ArangoDBHelper(settings.VIEW_NAME, self.request)
        binds = {
            "@view": settings.VIEW_NAME,
            "feed_identities": self.feed_identities,
        }
        more_filters = []
        if name := helper.query.get('name'):
            binds['name'] = "%" + name.replace('%', r'\%') + "%"
            more_filters.append('FILTER doc.name LIKE @name')
        more_filters.append("FILTER doc.id IN @feed_identities")

        query = """
        FOR doc IN @@view
        SEARCH doc.type == "identity" AND doc._is_latest == TRUE
        #more_filters

        COLLECT id = doc.id INTO docs LET doc = docs[0].doc
        #sort_stmt
        LIMIT @offset, @count
        RETURN KEEP(doc, KEYS(doc, TRUE))
        """
    
        query = query.replace(
            '#sort_stmt', helper.get_sort_stmt(
                self.SORT_PROPERTIES
            )
        ).replace('#more_filters', '\n'.join(more_filters))
        return helper.execute_query(query, bind_vars=binds)
        
    def retrieve(self, request, *args, identity_id=None, **kwargs):
        helper = ArangoDBHelper(settings.VIEW_NAME, self.request)
        binds = {
            "@view": settings.VIEW_NAME,
            "identity_id": identity_id,
        }
        query = """
        FOR doc IN @@view
        SEARCH doc.type == "identity" AND doc._is_latest == TRUE AND doc.id == @identity_id
        COLLECT id = doc.id INTO docs LET doc = docs[0].doc
        LIMIT @offset, @count
        RETURN KEEP(doc, KEYS(doc, TRUE))
        """
        return helper.execute_query(query, bind_vars=binds)

    @property
    def feed_identities(self):
        return [feed.identity['id'] for feed in FeedProfile.objects.all()]