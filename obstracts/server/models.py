import logging
import os
from types import SimpleNamespace
from django.db import models
from django.utils.text import slugify
import txt2stix, txt2stix.extractions
from django.core.exceptions import ValidationError
from dogesec_commons.stixifier.models import Profile

from django.db.models.signals import post_delete
from django.dispatch import receiver
from dogesec_commons.objects.helpers import ArangoDBHelper
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

class JobState(models.TextChoices):
    RETRIEVING = "retrieving"
    QUEUED     = "in-queue"
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
    
    @property
    def edge_collection(self):
        return self.collection_name + "_edge_collection"
    
    @property
    def vertex_collection(self):
        return self.collection_name + "_vertex_collection"
    


class File(models.Model):
    feed = models.ForeignKey(FeedProfile, on_delete=models.CASCADE, default=None, null=True)
    post_id = models.UUIDField(primary_key=True)
    markdown_file = models.FileField(upload_to=upload_to_func, null=True)
    summary = models.CharField(max_length=65535, null=True)
    profile = models.ForeignKey(Profile, on_delete=models.PROTECT, default=None, null=True)
    ai_describes_incident = models.BooleanField(default=None, null=True)
    ai_incident_summary = models.CharField(default=None, max_length=65535, null=True)
    ai_incident_classification = models.CharField(default=None, max_length=256, null=True)

    def __str__(self) -> str:
        return f'File(feed_id={self.feed_id}, post_id={self.post_id})'
    
    def delete(self, *args, **kwargs):
        self._deleted_directly = True
        return super().delete(*args, **kwargs)
    
    @property
    def report_id(self):
        return "report--" + str(self.post_id)
    

@receiver(post_delete, sender=File)
def remove_files(sender, instance: File, **kwargs):
    if not getattr(instance, '_deleted_directly', False):
        return False
    
    q = """
    LET removed_edges = (
        FOR de IN @@edge
        FILTER de._obstracts_post_id == @post_id
        REMOVE de IN @@edge
        RETURN de.id
    )

    LET removed_vertices = (
        FOR dv IN @@vertex
        FILTER dv._obstracts_post_id == @post_id
        REMOVE dv IN @@vertex
        RETURN dv.id
    )
    RETURN {removed_edges, removed_vertices}
    """
    out = ArangoDBHelper(None, SimpleNamespace(GET=dict(), query_params=SimpleNamespace(dict=lambda:dict()))).execute_query(q, {'@vertex': instance.feed.collection_name+'_vertex_collection', '@edge': instance.feed.collection_name+'_edge_collection', 'post_id': str(instance.post_id)}, paginate=False)
    logging.debug(f"POST's objects removed {out}")
    return True
    

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
    ai_content_check_variable = models.CharField(default=None, null=True)
    
    @property
    def feed_id(self):
        if not self.feed:
            return None
        return self.feed.id
