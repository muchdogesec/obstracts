import sys
from django.db import models
from django.contrib.postgres.fields import ArrayField
import uuid

# Create your models here.

class RelationshipMode(models.TextChoices):
    AI = "ai", "AI Relationship"
    STANDARD = "standard", "AI Relationship"

class Profile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    created = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=250)
    extractions = ArrayField(base_field=models.CharField(max_length=256), help_text="extraction id(s)")
    whitelists = ArrayField(base_field=models.CharField(max_length=256), help_text="whitelist id(s)")
    aliases = ArrayField(base_field=models.CharField(max_length=256), help_text="alias id(s)")
    relationship_mode = models.CharField(choices=RelationshipMode.choices, max_length=20, default=RelationshipMode.STANDARD)
    prettify_with_ai = models.BooleanField(default=False)
    extract_text_from_image = models.BooleanField(default=False)



class JobState(models.TextChoices):
    RETRIEVING = "retrieving"
    PROCESSING = "processing"
    PROCESSED = "processed"
    RETRIEVE_FAILED = "retrieve_failed"


class H4FState(models.TextChoices):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED  = "failed"

class Job(models.Model):
    id = models.UUIDField(primary_key=True)
    feed_id = models.UUIDField()
    created = models.DateTimeField(auto_now_add=True)
    state = models.CharField(choices=JobState.choices, max_length=20, default=JobState.RETRIEVING)
    h4f_status = models.CharField(default=H4FState.PENDING, choices=H4FState.choices, max_length=20)
    item_count = models.IntegerField(default=0)
    processed_items = models.IntegerField(default=0)
    failed_processes = models.IntegerField(default=0)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE)
