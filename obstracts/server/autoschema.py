from typing import List, Literal
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.plumbing import ResolvedComponent
from rest_framework.serializers import Serializer


class ObstractsAutoSchema(AutoSchema):
    def get_tags(self) -> List[str]:
        if hasattr(self.view, "openapi_tags"):
            return self.view.openapi_tags
        return super().get_tags()
    
    
    def _map_serializer(self, serializer, direction, bypass_extensions=False):
        if getattr(serializer, "get_schema", None):
            return serializer.get_schema()
        return super()._map_serializer(serializer, direction, bypass_extensions)
    
    