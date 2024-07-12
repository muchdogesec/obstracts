from rest_framework import serializers
from .models import Profile, Job
from drf_spectacular.utils import extend_schema_serializer

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = '__all__'

class T2SSerializer(serializers.Serializer):
    description = serializers.CharField()
    id = serializers.CharField()
    type = serializers.CharField()

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


