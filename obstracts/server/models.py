import logging
import os
from pathlib import Path
import sys
from typing import Iterable
from django.conf import settings
from django.db import models
from django.contrib.postgres.fields import ArrayField
import uuid
from django.utils.text import slugify
from urllib.parse import urlparse
from functools import partial
import txt2stix, txt2stix.extractions
from django.core.exceptions import ValidationError
from django.core import files

# Create your models here.

class RelationshipMode(models.TextChoices):
    AI = "ai", "AI Relationship"
    STANDARD = "standard", "Standard Relationship"

def validate_extractor(types, name):
    extractors = txt2stix.extractions.parse_extraction_config(
            txt2stix.txt2stix.INCLUDES_PATH
        ).values()
    for extractor in extractors:
        if name == extractor.slug and extractor.type in types:
            return True
    raise ValidationError(f"{name} does not exist", 400)


def upload_to_func(instance: 'File', filename):
    return os.path.join(str(instance.post_id), 'files', filename)


class File(models.Model):
    post_id = models.UUIDField(primary_key=True)
    markdown_file = models.FileField(upload_to=upload_to_func, null=True)


class FileImage(models.Model):
    report = models.ForeignKey(File, related_name='images', on_delete=models.CASCADE)
    file = models.ImageField(upload_to=upload_to_func)
    name = models.CharField(max_length=256)

    @property
    def post_id(self):
        return self.report.post_id

class Profile(models.Model):
    id = models.UUIDField(primary_key=True)
    created = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=250, unique=True)
    extractions = ArrayField(base_field=models.CharField(max_length=256, validators=[partial(validate_extractor, ["ai", "pattern", "lookup"])]), help_text="extraction id(s)")
    whitelists = ArrayField(base_field=models.CharField(max_length=256, validators=[partial(validate_extractor, ["whitelist"])]), help_text="whitelist id(s)", default=list)
    aliases = ArrayField(base_field=models.CharField(max_length=256, validators=[partial(validate_extractor, ["alias"])]), help_text="alias id(s)", default=list)
    relationship_mode = models.CharField(choices=RelationshipMode.choices, max_length=20, default=RelationshipMode.STANDARD)
    extract_text_from_image = models.BooleanField(default=False)
    defang = models.BooleanField(default=True)

    def save(self, *args, **kwargs) -> None:
        if not self.id:
            self.id = uuid.uuid5(settings.OBSTRACTS_NAMESPACE, self.name)
        return super().save(*args, **kwargs)


class JobState(models.TextChoices):
    RETRIEVING = "retrieving"
    PROCESSING = "processing"
    PROCESSED = "processed"
    PROCESS_FAILED = "processing_failed"
    RETRIEVE_FAILED = "retrieve_failed"


class H4FState(models.TextChoices):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED  = "failed"



class FeedProfile(models.Model):
    id = models.UUIDField(primary_key=True)
    collection_name = models.CharField(max_length=200)
    last_run = models.DateTimeField(null=True)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE)
    title = models.CharField(max_length=1000)

    def save(self, *args, **kwargs) -> None:
        self.collection_name = self.generate_collection_name()
        return super().save(*args, **kwargs)
    
    def generate_collection_name(self):
        if self.collection_name:
            return self.collection_name
        return f"{slugify(self.title)}_{self.id}".strip("_")

class Job(models.Model):
    id = models.UUIDField(primary_key=True)
    created = models.DateTimeField(auto_now_add=True)
    state = models.CharField(choices=JobState.choices, max_length=20, default=JobState.RETRIEVING)
    history4feed_status = models.CharField(default=H4FState.PENDING, choices=H4FState.choices, max_length=20)
    history4feed_job = models.JSONField(null=True)
    item_count = models.IntegerField(default=0)
    processed_items = models.IntegerField(default=0)
    failed_processes = models.IntegerField(default=0)
    feed = models.ForeignKey(FeedProfile, on_delete=models.CASCADE, null=True)
    profile = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True)
    
    @property
    def feed_id(self):
        if not self.feed:
            return None
        return self.feed.id
