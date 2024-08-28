import typing
from arango import ArangoClient
from django.conf import settings
from ..utils import Pagination, Response
from drf_spectacular.utils import OpenApiParameter

if typing.TYPE_CHECKING:
    from obstracts import settings


class ArangoDBHelper:
    max_page_size = settings.MAXIMUM_PAGE_SIZE
    page_size = settings.DEFAULT_PAGE_SIZE


    def query_as_array(self, key):
        query = self.query.get(key)
        if not query:
            return []
        return query.split(',')
    
    def query_as_bool(self, key, default=True):
        query_str = self.query.get(key)
        if not query_str:
            return default
        return query_str.lower() == 'true'

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

    def execute_query(self, query, bind_vars={}, paginate=True):
        if paginate:
            bind_vars['offset'], bind_vars['count'] = self.get_offset_and_count(self.count, self.page)
        cursor = self.db.aql.execute(query, bind_vars=bind_vars, count=True)
        if paginate:
            return self.get_paginated_response(cursor, self.page, self.page_size)
        return list(cursor)

    def get_offset_and_count(self, count, page) -> tuple[int, int]:
        page = page or 1
        offset = (page-1)*count
        return offset, count
    
    def get_reports(self, id=None):
        bind_vars = {
                "@collection": self.collection,
                "type": 'report',
        }
        query = """
            FOR doc in @@collection
            FILTER doc.type == @type AND doc._is_latest
            LIMIT @offset, @count
            RETURN KEEP(doc, KEYS(doc, true))
        """
        return self.execute_query(query, bind_vars=bind_vars)
    
    def get_report_by_id(self, id):
        bind_vars = {
                "@collection": self.collection,
                "id": id,
                'type': 'report',
        }
        query = """
            FOR doc in @@collection
            FILTER doc.id == @id AND doc._is_latest AND doc.type == @type
            LIMIT 1
            RETURN KEEP(doc, KEYS(doc, true))
        """
        return self.execute_query(query, bind_vars=bind_vars, paginate=False)
    
    def remove_report(self, id):
        bind_vars = {
                "@collection": self.collection,
                'report_id': id,
        }
        query = """
            FOR doc in @@collection
            FILTER doc._stixify_report_id == @report_id AND doc._is_latest
            RETURN doc._id
        """
        collections = {}
        out = self.execute_query(query, bind_vars=bind_vars, paginate=False)
        for key in out:
            collection, key = key.split('/', 2)
            collections[collection] = collections.get(collection, [])
            collections[collection].append(key)

        deletion_query = """
            FOR _key in @objects
            REMOVE {_key} IN @@collection
            RETURN _key
        """

        for collection, objects in collections.items():
            bind_vars = {
                "@collection": collection,
                "objects": objects,
            }
            self.execute_query(deletion_query, bind_vars, paginate=False)
        
    def get_scos(self, matcher={}):
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
        other_filters = []

        if new_types := self.query_as_array('types'):
            types = set(new_types)
        bind_vars = {
                "@collection": self.collection,
                "types": list(types),
        }
        if value := self.query.get('value'):
            bind_vars['search_value'] = value
            other_filters.append(
                """
                (
                    CONTAINS(doc.value, @search_value) OR
                    CONTAINS(doc.name, @search_value) OR
                    CONTAINS(doc.path, @search_value) OR
                    CONTAINS(doc.key, @search_value) OR
                    CONTAINS(doc.number, @search_value) OR
                    CONTAINS(doc.string, @search_value) OR
                    CONTAINS(doc.hash, @search_value) OR
                    CONTAINS(doc.symbol, @search_value) OR
                    CONTAINS(doc.address, @search_value) OR
                    (doc.type == 'file' AND @search_value IN doc.hashes)
                )
                """.strip()
            )

        # if post_id := self.query.get('post_id'):
        #     matcher["_obstracts_post_id"] = post_id

        # if report_id := self.query.get('report_id'):
        #     matcher["_stixify_report_id"] = report_id

        if matcher:
            bind_vars['matcher'] = matcher
            other_filters.insert(0, "MATCHES(doc, @matcher)")


        if other_filters:
            other_filters = "FILTER " + " AND ".join(other_filters)

        query = f"""
            FOR doc in @@collection
            FILTER CONTAINS(@types, doc.type) AND doc._is_latest
            {other_filters or ""}


            LIMIT @offset, @count
            RETURN KEEP(doc, KEYS(doc, true))
        """
        return self.execute_query(query, bind_vars=bind_vars)

    def get_sdos(self):
        types = set([
            "report",
            "note",
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
        # if new_types := self.query_as_array('types'):
        #     types = set(new_types)
        
        if self.query_as_bool('hide_processing_notes', False):
            types.remove('note')

        bind_vars = {
            "@collection": self.collection,
            "types": list(types),
        }
        other_filters = []
        if term := self.query.get('labels'):
            bind_vars['labels'] = term
            other_filters.append("COUNT(doc.labels[* CONTAINS(CURRENT, @labels)]) != 0")

        if term := self.query.get('name'):
            bind_vars['name'] = term
            other_filters.append("CONTAINS(doc.name, @name)")

        if other_filters:
            other_filters = "FILTER " + " AND ".join(other_filters)

        query = f"""
            FOR doc in @@collection
            FILTER doc.type IN @types AND doc._is_latest
            {other_filters or ""}


            LIMIT @offset, @count
            RETURN  KEEP(doc, KEYS(doc, true))
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
            RETURN KEEP(doc, KEYS(doc, true))
        """
        return self.execute_query(query, bind_vars=bind_vars)
    
    def get_sros(self):
        bind_vars = {
            "@collection": self.collection,
        }

        other_filters = []

        if term := self.query.get('source_ref'):
            bind_vars['source_ref'] = term
            other_filters.append('doc.source_ref == @source_ref')
        
        if terms := self.query_as_array('source_ref_type'):
            bind_vars['source_ref_type'] = terms
            other_filters.append('SPLIT(doc.source_ref, "--")[0] IN @source_ref_type')
        
        if term := self.query.get('target_ref'):
            bind_vars['target_ref'] = term
            other_filters.append('doc.target_ref == @target_ref')
            
        if terms := self.query_as_array('target_ref_type'):
            bind_vars['target_ref_type'] = terms
            other_filters.append('SPLIT(doc.target_ref, "--")[0] IN @target_ref_type')

        if term := self.query.get('relationship_type'):
            bind_vars['relationship_type'] = term
            other_filters.append("CONTAINS(doc.relationship_type, @relationship_type)")
    
        if other_filters:
            other_filters = "FILTER " + " AND ".join(other_filters)
        else:
            other_filters = ""

        query = f"""
            FOR doc in @@collection
            FILTER doc.type == 'relationship' AND doc._is_latest
            {other_filters}

            LIMIT @offset, @count
            RETURN KEEP(doc, KEYS(doc, true))

        """
        print(query, bind_vars)
        return self.execute_query(query, bind_vars=bind_vars)
    
    
    def get_post_objects(self, post_id, feed_id):
        types = self.query.get('types', "")
        bind_vars = {
            "@view": self.collection,
            "matcher": dict(_obstracts_post_id=str(post_id), _obstracts_feed_id=str(feed_id)),
            "types": types.split(",") if types else None
        }
        query = """
            FOR doc in @@view
            FILTER doc._is_latest AND MATCHES(doc, @matcher)
            FILTER doc.type IN @types OR NOT @types

            LIMIT @offset, @count
            RETURN KEEP(doc, KEYS(doc, true))
        """
        print(bind_vars, self.query.get('types', ""), True)
        return self.execute_query(query, bind_vars=bind_vars)
    


    def remove_matches(self, matcher):
        bind_vars = {
                "@collection": self.collection,
                'matcher': matcher,
        }
        query = """
            FOR doc in @@collection
            FILTER MATCHES(doc, @matcher)
            RETURN doc._id
        """
        collections = {}
        out = self.execute_query(query, bind_vars=bind_vars, paginate=False)
        for key in out:
            collection, key = key.split('/', 2)
            collections[collection] = collections.get(collection, [])
            collections[collection].append(key)

        deletion_query = """
        LET removed_@var = (
            FOR _key in @objects_@var
            REMOVE {_key} IN @@collection_@var
            RETURN _key
        )
        """
        queries = []
        bind_vars = {}
        for collection, objects in collections.items():
            queries.append(deletion_query.replace('@var', collection))
            
            bind_vars.update({
                "@collection_"+collection: collection,
                "objects_"+collection: objects,
            })
        queries.append('\nRETURN NULL')
        deletion_query = "\n\n".join(queries)
        print(deletion_query)
        self.execute_query(deletion_query, bind_vars, paginate=False)
        