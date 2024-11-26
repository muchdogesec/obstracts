import uuid
from rest_framework import serializers

from obstracts.server import h4fserializers
from .models import Profile, Job, FileImage
from drf_spectacular.utils import extend_schema_field
from django.utils.translation import gettext_lazy as _
from dogesec_commons.stixifier.summarizer import parse_summarizer_model


class JobSerializer(serializers.ModelSerializer):
    feed_id = serializers.PrimaryKeyRelatedField(read_only=True, source='feed')
    profile_id = serializers.PrimaryKeyRelatedField(read_only=True, source='profile')
    class Meta:
        model = Job
        # fields = "__all__"
        exclude = ["feed", "profile"]

class ProfileIDField(serializers.PrimaryKeyRelatedField):
    def __init__(self, **kwargs):
        super().__init__(queryset=Profile.objects, error_messages={
                'required': _('This field is required.'),
                'does_not_exist': _('Invalid profile with id "{pk_value}" - object does not exist.'),
                'incorrect_type': _('Incorrect type. Expected profile id (uuid), received {data_type}.'),
            },**kwargs)
        
    def to_internal_value(self, data):
        return super().to_internal_value(data).pk
    
    def to_representation(self, value):
        if isinstance(value, uuid.UUID):
            return value
        return super().to_representation(value)

class CreateTaskSerializer(serializers.Serializer):
    profile_id = ProfileIDField(help_text="profile id to use")
    ai_summary_provider = serializers.CharField(allow_blank=True, allow_null=True, validators=[parse_summarizer_model], default=None, write_only=True, help_text="AI Summary provider int the format provider:model e.g `openai:gpt-3.5-turbo`")

class FeedSerializer(CreateTaskSerializer, h4fserializers.FeedXSerializer):
    pass

class SkeletonFeedSerializer(h4fserializers.SkeletonFeedXSerializer):
    pass

class PatchSkeletonFeedSerializer(SkeletonFeedSerializer):
    url = None

class PatchFeedSerializer(FeedSerializer):
    url = None

class PatchPostSerializer(CreateTaskSerializer):
    pass

class PostCreateSerializer(PatchPostSerializer):
    title = serializers.CharField()
    link = serializers.URLField()
    pubdate = serializers.DateTimeField()
    author = serializers.CharField(required=False)
    categories = serializers.ListField(child=serializers.CharField(), required=False)


class ImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    class Meta:
        model = FileImage
        fields = ["name", "url"]

    @extend_schema_field(serializers.CharField())
    def get_url(self, instance):
        request = self.context.get('request')
        if instance.file and hasattr(instance.file, 'url'):
            photo_url = instance.file.url
            return request.build_absolute_uri(photo_url)
        return None
