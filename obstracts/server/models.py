import sys
from typing import Iterable
from django.db import models
from django.contrib.postgres.fields import ArrayField
import uuid
from django.utils.text import slugify
from urllib.parse import urlparse

# Create your models here.

class RelationshipMode(models.TextChoices):
    AI = "ai", "AI Relationship"
    STANDARD = "standard", "Standard Relationship"

class Profile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    created = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=250, unique=True)
    extractions = ArrayField(base_field=models.CharField(max_length=256), help_text="extraction id(s)")
    whitelists = ArrayField(base_field=models.CharField(max_length=256), help_text="whitelist id(s)", default=list)
    aliases = ArrayField(base_field=models.CharField(max_length=256), help_text="alias id(s)", default=list)
    relationship_mode = models.CharField(choices=RelationshipMode.choices, max_length=20, default=RelationshipMode.STANDARD)
    prettify_with_ai = models.BooleanField(default=False)
    extract_text_from_image = models.BooleanField(default=False)



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
    item_count = models.IntegerField(default=0)
    processed_items = models.IntegerField(default=0)
    failed_processes = models.IntegerField(default=0)
    feed = models.ForeignKey(FeedProfile, on_delete=models.CASCADE, null=True)

    @property
    def profile(self) -> Profile:
        return self.feed.profile
    
    @property
    def feed_id(self):
        if not self.feed:
            return None
        return self.feed.id
