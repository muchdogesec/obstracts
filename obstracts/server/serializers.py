from rest_framework import serializers
from .models import Profile, Job, FileImage
from drf_spectacular.utils import extend_schema_serializer, extend_schema_field
from django.utils.translation import gettext_lazy as _
from dogesec_commons.stixifier.summarizer import parse_summarizer_model


class JobSerializer(serializers.ModelSerializer):
    feed_id = serializers.PrimaryKeyRelatedField(read_only=True, source='feed')
    profile_id = serializers.PrimaryKeyRelatedField(read_only=True, source='profile')
    class Meta:
        model = Job
        # fields = "__all__"
        exclude = ["feed", "profile"]

class CreateTaskSerializer(serializers.Serializer):
    profile_id = serializers.PrimaryKeyRelatedField(queryset=Profile.objects, error_messages={
        'required': _('This field is required.'),
        'does_not_exist': _('Invalid profile with id "{pk_value}" - object does not exist.'),
        'incorrect_type': _('Incorrect type. Expected profile id (uuid), received {data_type}.'),
    })
    ai_summary_provider = serializers.CharField(allow_blank=True, allow_null=True, validators=[parse_summarizer_model], default=None)

class FeedSerializer(CreateTaskSerializer):
    url = serializers.URLField(help_text="The URL of the RSS or ATOM feed")
    include_remote_blogs = serializers.BooleanField(help_text="", default=False, required=False)

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

class H4fFeedSerializer(serializers.Serializer):
    def get_schema(self):
        true, false = True, False
        return {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "format": "uuid",
                        "readOnly": true,
                        "description": "UUID of feed generated by history4feed"
                    },
                    "count_of_posts": {
                        "type": "integer",
                        "readOnly": true,
                        "description": "Number of posts in feed"
                    },
                    "profile_id": {
                        "type": "string",
                        "format": "uuid",
                        "writeOnly": true,
                        "nullable": true
                    },
                    "include_remote_blogs": {
                        "type": "boolean",
                        "writeOnly": true,
                        "default": false
                    },
                    "title": {
                        "type": "string",
                        "readOnly": true,
                        "description": "found in the <channel> of RSS output. Is always kept up to date with the latest feed import values for this property."
                    },
                    "description": {
                        "type": "string",
                        "readOnly": true,
                        "description": "found in the <channel> of RSS output. Is always kept up to date with the latest feed import values for this property."
                    },
                    "url": {
                        "type": "string",
                        "format": "uri",
                        "description": "\nThe URL of the RSS or ATOM feed\n\nNote this will be validated to ensure the feed is in the correct format.\n",
                        "maxLength": 1000
                    },
                    "earliest_item_pubdate": {
                        "type": "string",
                        "format": "date-time",
                        "readOnly": true,
                        "nullable": true,
                        "description": "pubdate of earliest post"
                    },
                    "latest_item_pubdate": {
                        "type": "string",
                        "format": "date-time",
                        "readOnly": true,
                        "nullable": true,
                        "description": "pubdate of latest post"
                    },
                    "datetime_added": {
                        "type": "string",
                        "format": "date-time",
                        "readOnly": true,
                        "description": "date feed entry was added to database"
                    },
                    "feed_type": {
                        "type": "string",
                        "readOnly": true,
                        "description": "type of feed"
                    }
                },
                "required": [
                    "count_of_posts",
                    "datetime_added",
                    "description",
                    "earliest_item_pubdate",
                    "feed_type",
                    "id",
                    "latest_item_pubdate",
                    "title",
                    "url"
                ]
            }


class H4fPostSerializer(serializers.Serializer):
    def get_schema(self):
        true, false = True, False
        return {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "format": "uuid",
                    "readOnly": true,
                    "description": "UUID of items generated by history4feed"
                },
                "profile_id": {
                    "type": "string",
                    "format": "uuid"
                },
                "datetime_added": {
                    "type": "string",
                    "format": "date-time",
                    "readOnly": true
                },
                "datetime_updated": {
                    "type": "string",
                    "format": "date-time",
                    "readOnly": true
                },
                "title": {
                    "type": "string",
                    "description": "found in the <item> element of feed output",
                    "maxLength": 1000
                },
                "description": {
                    "type": "string",
                    "readOnly": true,
                    "description": "found in the <item> element of feed output"
                },
                "link": {
                    "type": "string",
                    "format": "uri",
                    "description": "link to full article. found in the <item> element of feed output",
                    "maxLength": 1000
                },
                "pubdate": {
                    "type": "string",
                    "format": "date-time",
                    "description": "date of publication."
                },
                "author": {
                    "type": "string",
                    "description": "author of the post",
                    "maxLength": 1000
                },
                "is_full_text": {
                    "type": "boolean",
                    "readOnly": true,
                    "description": "if full text has been retrieved"
                },
                "content_type": {
                    "type": "string",
                    "readOnly": true,
                    "description": "content type of the description"
                },
                "added_manually": {
                    "type": "boolean"
                },
                "categories": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "categories of the post"
                }
            },
            "required": [
                "author",
                "content_type",
                "datetime_added",
                "datetime_updated",
                "description",
                "id",
                "is_full_text",
                "link",
                "pubdate",
                "title"
            ]
        }


class ErrorSerializer(serializers.Serializer):
    message = serializers.CharField(required=True)
    code    = serializers.IntegerField(required=True)
    details = serializers.DictField(required=False)