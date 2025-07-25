import uuid
from rest_framework import serializers


from history4feed.app import serializers as h4fserializers
from .models import File, Profile, Job, FileImage
from drf_spectacular.utils import extend_schema_field
from django.utils.translation import gettext_lazy as _


class ObstractsJobSerializer(serializers.ModelSerializer):
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
    profile_id = ProfileIDField(help_text="profile id to use", write_only=True, required=True)

class FeedCreateSerializer(CreateTaskSerializer, h4fserializers.FeedSerializer):
    count_of_posts = serializers.IntegerField(source='obstracts_feed.visible_posts_count', read_only=True, help_text="Number of posts in feed")

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


class ObstractsPostSerializer(h4fserializers.PostSerializer):
    profile_id = serializers.UUIDField(source='obstracts_post.profile_id', required=False, allow_null=True)
    ai_describes_incident = serializers.BooleanField(source='obstracts_post.ai_describes_incident', required=False, read_only=True, allow_null=True)
    ai_incident_summary = serializers.CharField(source='obstracts_post.ai_incident_summary', required=False, read_only=True, allow_null=True)
    ai_incident_classification = serializers.ListField(source='obstracts_post.ai_incident_classification', required=False, read_only=True, allow_null=True)
    summary = serializers.CharField(source='obstracts_post.summary', read_only=True, required=False, allow_null=True)
    visible = serializers.BooleanField(source='obstracts_post.processed', read_only=True, required=False, allow_null=True)
    archived_pdf = serializers.FileField(source='obstracts_post.pdf_file', read_only=True, required=False, allow_null=True)


class PostWithFeedIDSerializer(ObstractsPostSerializer):
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

class AttackNavigatorSerializer(serializers.Serializer):
    mobile = serializers.DictField(required=False)
    ics = serializers.DictField(required=False)
    enterprise = serializers.DictField(required=False)