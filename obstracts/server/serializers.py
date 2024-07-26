from rest_framework import serializers
from .models import Profile, Job
from drf_spectacular.utils import extend_schema_serializer

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = '__all__'

class T2SSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    type = serializers.CharField()
    description = serializers.CharField()
    notes = serializers.CharField()
    file = serializers.CharField()
    created = serializers.CharField()
    modified = serializers.CharField()
    created_by = serializers.CharField()
    version = serializers.CharField()

class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = '__all__'


class FeedSerializer(serializers.Serializer):
    profile_id = serializers.CharField()
    url = serializers.URLField(help_text="The URL of the RSS or ATOM feed")

extend_schema_serializer(many=False)
class StixObjectSerializer(serializers.Serializer):
    please = serializers.CharField()


