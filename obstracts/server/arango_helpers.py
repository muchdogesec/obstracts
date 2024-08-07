from arango import ArangoClient
from arango.job import AsyncJob
from arango.cursor import Cursor as ArangoCursor
from django.conf import settings
from .utils import Pagination, Response
from drf_spectacular.utils import OpenApiParameter


class ArangoDBHelper:
    max_page_size = 500
    page_size = 100

    @classmethod
    def get_page_params(cls, request):
        kwargs = request.GET.copy()
        page_number = int(kwargs.get('page', 1))
        page_limit  = min(int(kwargs.get('page_size', ArangoDBHelper.page_size)), ArangoDBHelper.max_page_size)
        return page_number, page_limit

    @classmethod
    def get_paginated_response(cls, data, page_number, page_size=page_size):
        return Response(
            {
                "page_size": page_size or cls.page_size,
                "page_number": page_number,
                "page_results_count": len(data),
                "objects": data,
            }
        )

    @classmethod
    def get_paginated_response_schema(cls):
        return {
            200: {
                "type": "object",
                "required": ["page_results_count", "objects"],
                "properties": {
                    "page_size": {
                        "type": "integer",
                        "example": cls.max_page_size,
                    },
                    "page_number": {
                        "type": "integer",
                        "example": 3,
                    },
                    "page_results_count": {
                        "type": "integer",
                        "example": cls.page_size,
                    },
                    "objects": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type":{
                                    "example": "domain-name",
                                },
                                "id": {
                                    "example": "domain-name--a86627d4-285b-5358-b332-4e33f3ec1075",
                                },
                            },
                            "additionalProperties": True,
                        }
                    }
                }
            }
        }

    @classmethod
    def get_schema_operation_parameters(self):
        parameters = [
            OpenApiParameter(
                Pagination.page_query_param,
                type=int,
                description=Pagination.page_query_description,
            ),
            OpenApiParameter(
                Pagination.page_size_query_param,
                type=int,
                description=Pagination.page_size_query_description,
            ),
        ]
        return parameters




    client = ArangoClient(
        hosts=settings.ARANGODB_HOST_URL
    )
    DB_NAME = f"{settings.ARANGODB_DATABASE}_database"

    def __init__(self, collection, request) -> None:
        self.collection = collection
        self.db = self.client.db(
            self.DB_NAME,
            username=settings.ARANGODB_USERNAME,
            password=settings.ARANGODB_PASSWORD,
        )
        self.page, self.count = self.get_page_params(request)
        self.request = request
        self.query = request.query_params.dict()

    def execute_query(self, query, bind_vars={}):
        bind_vars['offset'], bind_vars['count'] = self.get_offset_and_count(self.count, self.page)
        cursor = self.db.aql.execute(query, bind_vars=bind_vars, count=True)
        return self.get_paginated_response(cursor, self.page, self.page_size)

    def get_offset_and_count(self, count, page) -> tuple[int, int]:
        page = page or 1
        offset = (page-1)*count
        return offset, count

    def get_scos(self):
        types = set([
            "ipv4-addr",
            "network-traffic",
            "ipv6-addr",
            "domain-name",
            "url",
            "file",
            "directory",
            "email-addr",
            "mac-addr",
            "windows-registry-key",
            "autonomous-system",
            "user-agent",
            "cryptocurrency-wallet",
            "cryptocurrency-transaction",
            "bank-card",
            "bank-account",
            "phone-number",
        ])
        bind_vars = {
                "@collection": self.collection,
                "types": list(types),
        }
        query = """
            FOR doc in @@collection
            FILTER CONTAINS(@types, doc.type) AND doc._is_latest


            LIMIT @offset, @count
            RETURN doc
        """
        return self.execute_query(query, bind_vars=bind_vars)

    def get_sdos(self):
        types = set([
            "report",
            "notes",
            "indicator",
            "attack-pattern",
            "weakness",
            "campaign",
            "course-of-action",
            "infrastructure",
            "intrusion-set",
            "malware",
            "threat-actor",
            "tool",
            "identity",
            "location",
        ])
        bind_vars = {
            "@collection": self.collection,
            "types": list(types),
        }
        query = """
            FOR doc in @@collection
            FILTER CONTAINS(@types, doc.type) AND doc._is_latest


            LIMIT @offset, @count
            RETURN doc
        """
        return self.execute_query(query, bind_vars=bind_vars)
    
    def get_objects_by_id(self, id):
        bind_vars = {
            "@view": self.collection,
            "id": id,
        }
        query = """
            FOR doc in @@view
            FILTER doc.id == @id AND doc._is_latest
            // LIMIT 1
            RETURN doc
        """
        return self.execute_query(query, bind_vars=bind_vars)
    
    def get_sros(self):
        bind_vars = {
            "@collection": self.collection,
        }
        query = """
            FOR doc in @@collection
            FILTER doc.type == 'relationship' AND doc._is_latest


            LIMIT @offset, @count
            RETURN doc
        """
        return self.execute_query(query, bind_vars=bind_vars)
    
    def get_post_objects(self, post_id):
        bind_vars = {
            "@view": self.collection,
            "note": f"obstracts-post--{post_id}",
            "types": self.query.get('types', "").split(",")
        }
        query = """
            FOR doc in @@view
            FILTER doc._is_latest AND doc._stix2arango_note == @note
            FILTER @types AND doc.type IN @types

            LIMIT @offset, @count
            RETURN doc
        """
        return self.execute_query(query, bind_vars=bind_vars)