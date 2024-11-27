import os
from django.db import models
from django.utils.text import slugify
import txt2stix, txt2stix.extractions
from django.core.exceptions import ValidationError
from dogesec_commons.stixifier.models import Profile
# Create your models here.


def validate_extractor(types, name):
    extractors = txt2stix.extractions.parse_extraction_config(
            txt2stix.txt2stix.INCLUDES_PATH
        ).values()
    for extractor in extractors:
        if name == extractor.slug and extractor.type in types:
            return True
    raise ValidationError(f"{name} does not exist", 400)


def upload_to_func(instance: 'File|FileImage', filename):
    if isinstance(instance, FileImage):
        instance = instance.report
    return os.path.join(str(instance.feed.id), 'posts', str(instance.post_id), filename)

class File(models.Model):
    post_id = models.UUIDField(primary_key=True)
    markdown_file = models.FileField(upload_to=upload_to_func, null=True)
    summary = models.CharField(max_length=65535, null=True)

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
    profile = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True)
    title = models.CharField(max_length=1000)

    def save(self, *args, **kwargs) -> None:
        self.collection_name = self.generate_collection_name()
        return super().save(*args, **kwargs)
    
    def generate_collection_name(self):
        if self.collection_name:
            return self.collection_name
        slug = slugify(self.title).replace('-', '_')
        return f"{slug}_{self.id}".strip("_").replace('-', '')
    


class File(models.Model):
    feed = models.ForeignKey(FeedProfile, on_delete=models.CASCADE, default=None, null=True)
    post_id = models.UUIDField(primary_key=True)
    markdown_file = models.FileField(upload_to=upload_to_func, null=True)
    summary = models.CharField(max_length=65535, null=True)
    profile = models.ForeignKey(Profile, on_delete=models.PROTECT, default=None, null=True)
    ai_summary_provider = models.CharField(null=True, default=None, max_length=256)

class FileImage(models.Model):
    report = models.ForeignKey(File, related_name='images', on_delete=models.CASCADE)
    file = models.ImageField(upload_to=upload_to_func)
    name = models.CharField(max_length=256)

    @property
    def post_id(self):
        return self.report.post_id

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
