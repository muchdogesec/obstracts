from typing import List
from drf_spectacular.openapi import AutoSchema

class ObstractsAutoSchema(AutoSchema):
    def get_tags(self) -> List[str]:
        if hasattr(self.view, "openapi_tags"):
            return self.view.openapi_tags
        return super().get_tags()
    
    