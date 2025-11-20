from enum import StrEnum, auto
import uuid
from rest_framework import serializers


from history4feed.app import serializers as h4fserializers
from .models import File, PDFCookieConsentMode, Profile, Job, FileImage
from drf_spectacular.utils import extend_schema_field
from django.utils.translation import gettext_lazy as _


class ObstractsJobSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField()
    feed_id = serializers.PrimaryKeyRelatedField(read_only=True, source="feed")
    profile_id = serializers.PrimaryKeyRelatedField(read_only=True, source="profile", required=False, allow_null=True)

    class Meta:
        model = Job
        # fields = "__all__"
        exclude = ["feed", "profile", "history4feed_job"]


class ProfileIDField(serializers.PrimaryKeyRelatedField):
    def __init__(self, **kwargs):
        super().__init__(
            queryset=Profile.objects,
            error_messages={
                "required": _("This field is required."),
                "does_not_exist": _(
                    'Invalid profile with id "{pk_value}" - object does not exist.'
                ),
                "incorrect_type": _(
                    "Incorrect type. Expected profile id (uuid), received {data_type}."
                ),
            },
            **kwargs,
        )

    def to_internal_value(self, data):
        return super().to_internal_value(data).pk

    def to_representation(self, value):
        if isinstance(value, uuid.UUID):
            return value
        return super().to_representation(value)


class CreateTaskSerializer(serializers.Serializer):
    profile_id = ProfileIDField(
        help_text="profile id to use", write_only=True, required=True
    )


class FeedCreateSerializer(CreateTaskSerializer, h4fserializers.FeedSerializer):
    count_of_posts = serializers.IntegerField(
        read_only=True,
        help_text="Number of posts in feed",
    )
    pdfshift_cookie_settings = serializers.ChoiceField(choices=PDFCookieConsentMode.choices, default=PDFCookieConsentMode.disable_all_js, source='obstracts_feed.pdfshift_cookie_settings')


class SkeletonFeedSerializer(h4fserializers.SkeletonFeedSerializer):
    pdfshift_cookie_settings = serializers.ChoiceField(choices=PDFCookieConsentMode.choices, default=PDFCookieConsentMode.disable_all_js, source='obstracts_feed.pdfshift_cookie_settings')



class PatchFeedSerializer(serializers.ModelSerializer):
    title = serializers.CharField(required=True, help_text="title of feed")
    description = serializers.CharField(required=True, help_text="description of feed")
    pdfshift_cookie_settings = serializers.ChoiceField(choices=PDFCookieConsentMode.choices, default=PDFCookieConsentMode.disable_all_js)

    class Meta:
        model = h4fserializers.FeedSerializer.Meta.model
        fields = ['title', 'description', 'pretty_url', 'pdfshift_cookie_settings']


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
    posts = serializers.ListSerializer(
        child=H4fPostCreateSerializer(), allow_empty=False
    )


class ObstractsPostSerializer(h4fserializers.PostSerializer):
    profile_id = serializers.UUIDField(
        source="obstracts_post.profile_id", required=False, allow_null=True
    )
    ai_describes_incident = serializers.BooleanField(
        source="obstracts_post.ai_describes_incident",
        required=False,
        read_only=True,
        allow_null=True,
    )
    ai_incident_summary = serializers.CharField(
        source="obstracts_post.ai_incident_summary",
        required=False,
        read_only=True,
        allow_null=True,
    )
    ai_incident_classification = serializers.ListField(
        source="obstracts_post.ai_incident_classification",
        required=False,
        read_only=True,
        allow_null=True,
    )
    summary = serializers.CharField(
        source="obstracts_post.summary", read_only=True, required=False, allow_null=True
    )
    visible = serializers.BooleanField(
        source="obstracts_post.processed",
        read_only=True,
        required=False,
        allow_null=True,
    )
    archived_pdf = serializers.FileField(
        source="obstracts_post.pdf_file",
        read_only=True,
        required=False,
        allow_null=True,
    )


class PostWithFeedIDSerializer(ObstractsPostSerializer):
    feed_id = serializers.UUIDField(help_text="containing feed's id")


class ImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = FileImage
        fields = ["name", "url"]

    @extend_schema_field(serializers.CharField())
    def get_url(self, instance):
        request = self.context.get("request")
        if instance.file and hasattr(instance.file, "url"):
            photo_url = instance.file.url
            return request.build_absolute_uri(photo_url)
        return None


class AttackNavigatorSerializer(serializers.Serializer):
    mobile = serializers.BooleanField(default=False)
    ics = serializers.BooleanField(default=False)
    enterprise = serializers.BooleanField(default=False)


from dogesec_commons.utils.serializers import JSONSchemaSerializer


class AttackNavigatorDomainSerializer(JSONSchemaSerializer):
    json_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "MITRE ATT&CK Navigator Layer v4.5",
        "type": "object",
        "required": ["version", "name", "domain", "techniques"],
        "properties": {
            "version": {"type": "string", "enum": ["4.5"]},
            "name": {"type": "string"},
            "domain": {
                "type": "string",
                "enum": ["enterprise-attack", "mobile-attack", "ics-attack"],
            },
            "description": {"type": "string"},
            "gradient": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["color", "minValue", "maxValue"],
                    "properties": {
                        "color": {"type": "string", "pattern": "^#[0-9A-Fa-f]{6}$"},
                        "minValue": {"type": "number"},
                        "maxValue": {"type": "number"},
                    },
                },
            },
            "legendItems": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "color": {"type": "string", "pattern": "^#[0-9A-Fa-f]{6}$"},
                        "value": {"type": "number"},
                    },
                },
            },
            "showTacticsRowBackground": {"type": "boolean"},
            "techniques": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["techniqueID"],
                    "properties": {
                        "techniqueID": {"type": "string"},
                        "score": {"type": ["number", "null"]},
                        "color": {"type": "string", "pattern": "^#[0-9A-Fa-f]{6}$"},
                        "comment": {"type": "string"},
                        "enabled": {"type": "boolean"},
                        "links": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "href": {"type": "string", "format": "uri"},
                                    "text": {"type": "string"},
                                },
                                "required": ["href", "text"],
                            },
                        },
                    },
                    "additionalProperties": False,
                },
            },
            "tacticUseIds": {"type": "array", "items": {"type": "string"}},
            "filters": {
                "type": "object",
                "properties": {
                    "includeSubtechniques": {"type": "boolean"},
                    "showOnlyVisibleTechniques": {"type": "boolean"},
                },
            },
        },
        "additionalProperties": True,
    }



class HealthCheckChoices(StrEnum):
    AUTHORIZED = auto()
    UNAUTHORIZED = auto()
    UNSUPPORTED = auto()
    NOT_CONFIGURED = "not-configured"
    UNKNOWN = auto()
    OFFLINE = auto()

class HealthCheckChoiceField(serializers.ChoiceField):
    def __init__(self, **kwargs):
        choices = [m.value for m in HealthCheckChoices]
        super().__init__(choices, **kwargs)
        
class HealthCheckLLMs(serializers.Serializer):
    openai = HealthCheckChoiceField()
    deepseek = HealthCheckChoiceField()
    anthropic = HealthCheckChoiceField()
    gemini = HealthCheckChoiceField()
    openrouter = HealthCheckChoiceField()

class HealthCheckSerializer(serializers.Serializer):
    ctibutler = HealthCheckChoiceField()
    vulmatch = HealthCheckChoiceField()
    btcscan = HealthCheckChoiceField()
    binlist = HealthCheckChoiceField()
    pdfshift = HealthCheckChoiceField()
    llms = HealthCheckLLMs()

