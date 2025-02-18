import uuid
from rest_framework import serializers


from history4feed.app import serializers as h4fserializers
from .models import File, Profile, Job, FileImage
from drf_spectacular.utils import extend_schema_field
from django.utils.translation import gettext_lazy as _
from dogesec_commons.stixifier.summarizer import parse_summarizer_model


class JobSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField()
    feed_id = serializers.PrimaryKeyRelatedField(read_only=True, source='feed')
    profile_id = serializers.PrimaryKeyRelatedField(read_only=True, source='profile')
    class Meta:
        model = Job
        # fields = "__all__"
        exclude = ["feed", "profile", "history4feed_job"]

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
    profile_id = ProfileIDField(help_text="profile id to use", write_only=True)

class FeedSerializer(CreateTaskSerializer, h4fserializers.FeedSerializer):
    pass

class SkeletonFeedSerializer(h4fserializers.SkeletonFeedSerializer):
    pass

class PatchFeedSerializer(SkeletonFeedSerializer):
    url = None

class FetchFeedSerializer(CreateTaskSerializer):
    include_remote_blogs = serializers.BooleanField(write_only=True, default=False)


class FetchPostSerializer(CreateTaskSerializer):
    pass

class H4fPostCreateSerializer(serializers.Serializer):
    title = serializers.CharField()
    link = serializers.URLField()
    pubdate = serializers.DateTimeField()
    author = serializers.CharField(required=False)
    categories = serializers.ListField(child=serializers.CharField(), required=False)

class PatchPostSerializer(H4fPostCreateSerializer):
    link = None

    
class PostCreateSerializer(CreateTaskSerializer):
    posts = serializers.ListSerializer(child=H4fPostCreateSerializer(), allow_empty=False)


class FileSerializer(h4fserializers.PostSerializer):
    profile_id = serializers.UUIDField(source='obstracts_post.profile_id', required=True)
    # class Meta:
    #     exclude = ["profile", "feed", "markdown_file"]




class PostWithFeedIDSerializer(FileSerializer):
    feed_id = serializers.UUIDField(help_text="containing feed's id")

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
