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
        hosts=f"http://{settings.ARANGODB_HOST}:{settings.ARANGODB_PORT}"
    )
    # verify that database exists
    client.db(
        settings.ARANGODB_DATABASE,
        username=settings.ARANGODB_USERNAME,
        password=settings.ARANGODB_PASSWORD,
        verify=True,
    )

    def __init__(self) -> None:
        self.collection = settings.ARANGODB_COLLECTION
        self.db = self.client.db(
            settings.ARANGODB_DATABASE,
            username=settings.ARANGODB_USERNAME,
            password=settings.ARANGODB_PASSWORD,
        )

    def execute_query(self, query, bind_vars={}, page=1, count=50):
        bind_vars['offset'], bind_vars['count'] = self.get_page(count, page)
        cursor = self.db.aql.execute(query, bind_vars=bind_vars, count=True)
        return cursor

    def get_page(self, count, page):
        page = page or 1
        offset = (page-1)*count
        return offset, count

    def get_scos(self, page, count=50):
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
                "@collection": f"{self.collection}_vertex_collection",
                "types": list(types),
        }
        query = """
            FOR doc in @@collection
                FILTER CONTAINS(@types, doc.type)


                LIMIT @offset, @count
                RETURN doc
        """
        return self.get_paginated_response(self.execute_query(query, bind_vars=bind_vars, page=page, count=count), page_number=page, page_size=count)

    def get_sdos(self, page, count=50):
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
            "@collection": f"{self.collection}_vertex_collection",
            "types": list(types),
        }
        query = """
            FOR doc in @@collection
                FILTER CONTAINS(@types, doc.type)


                LIMIT @offset, @count
                RETURN doc
        """
        return self.get_paginated_response(self.execute_query(query, bind_vars=bind_vars, page=page, count=count), page_number=page, page_size=count)
    
    def get_objects_by_id(self, id, page=1, count=50):
        bind_vars = {
            "@vertex_collection": f"{self.collection}_vertex_collection",
            "@edge_collection": f"{self.collection}_edge_collection",
            "id": id,
        }
        query = """
            LET vertices = (
                FOR doc in @@vertex_collection
                FILTER doc.id == @id
            )
            LET edges = (
                FOR doc in @@edge_collection
                FILTER doc.id == @id
            )

            FOR doc in APPEND(vertices, edges)

            LIMIT @offset, @count
            RETURN doc
        """
        return self.get_paginated_response(self.execute_query(query, bind_vars=bind_vars, page=page, count=count), page_number=page, page_size=count)

    def get_sros(self, page, count=50):
        bind_vars = {
            "@collection": f"{self.collection}_edge_collection",
        }
        query = """
            FOR doc in @@collection
                FILTER doc.type == 'relationship'


                LIMIT @offset, @count
                RETURN doc
        """
        return self.get_paginated_response(self.execute_query(query, bind_vars=bind_vars, page=page, count=count), page_number=page, page_size=count)