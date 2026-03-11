from rest_framework import serializers
from obstracts.server.models import ObjectValue

class ObjectValueSerializer(serializers.Serializer):
    """Serializer for ObjectValue model with aggregated post_ids."""
    
    id = serializers.CharField(source='stix_id')
    type = serializers.CharField()
    ttp_type = serializers.CharField(required=False)
    values = serializers.JSONField(read_only=True)
    matched_posts = serializers.ListField(child=serializers.UUIDField())
    created = serializers.DateTimeField(required=False)
    modified = serializers.DateTimeField(required=False)

    def to_representation(self, instance):
        """remove null fields from the output"""
        representation = super().to_representation(instance)
        representation = {k: v for k, v in representation.items() if v is not None}
        return representation