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
from history4feed.app import models as h4f_models
from history4feed.app.models import JobState as H4FState
from django.db.models.signals import post_save
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

class FeedProfile(models.Model):
    feed = models.OneToOneField(h4f_models.Feed, on_delete=models.CASCADE, primary_key=True, related_name="obstracts_feed")
    collection_name = models.CharField(max_length=200)
    last_run = models.DateTimeField(null=True)
    profile = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True)

    def save(self, *args, **kwargs) -> None:
        self.collection_name = self.generate_collection_name()
        return super().save(*args, **kwargs)
    
    def generate_collection_name(self):
        if self.collection_name:
            return self.collection_name
        title = self.title.strip() or 'blog'
        slug = slugify(title).replace('-', '_')
        return f"{slug}_{self.id}".strip("_").replace('-', '')
    
    @property
    def edge_collection(self):
        return self.collection_name + "_edge_collection"
    
    @property
    def vertex_collection(self):
        return self.collection_name + "_vertex_collection"
    
    @property
    def id(self):
        return self.feed.id
    
    @property
    def title(self) -> str:
        return h4f_models.title_as_string(self.feed.title)
    
@receiver(post_save, sender=h4f_models.Feed)
def auto_create_feed(sender, instance: h4f_models.Feed, **kwargs):
    feed, _ = FeedProfile.objects.update_or_create(feed=instance)
    
@receiver(post_save, sender=h4f_models.Job)
def start_job(sender, instance: h4f_models.Job, **kwargs):
    from ..cjob import tasks
    if instance.state not in [H4FState.SUCCESS, H4FState.FAILED]:
        return
    job: Job = instance.obstracts_job
    if instance.state == H4FState.SUCCESS:
        tasks.start_processing.delay(instance.id)
    if instance.state == H4FState.FAILED:
        job.state = JobState.RETRIEVE_FAILED
        job.save()
        


class File(models.Model):
    feed = models.ForeignKey(FeedProfile, on_delete=models.CASCADE, default=None, null=True)
    post = models.OneToOneField(h4f_models.Post, on_delete=models.CASCADE, primary_key=True, related_name="obstracts_post")

    markdown_file = models.FileField(upload_to=upload_to_func, null=True)
    summary = models.CharField(max_length=65535, null=True)
    profile = models.ForeignKey(Profile, on_delete=models.PROTECT, default=None, null=True)

    # describe incident
    ai_describes_incident = models.BooleanField(default=None, null=True)
    ai_incident_summary = models.CharField(default=None, max_length=65535, null=True)
    ai_incident_classification = models.CharField(default=None, max_length=256, null=True)

    def save(self, *args, **kwargs):
        self.post.save() #update datetime_updated
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f'File(feed_id={self.feed_id}, post_id={self.post_id})'
    
    def delete(self, *args, **kwargs):
        self._deleted_directly = True
        return super().delete(*args, **kwargs)
    
    @property
    def report_id(self):
        return "report--" + str(self.post_id)
    
FakeRequest = SimpleNamespace(GET=dict(), query_params=SimpleNamespace(dict=lambda:dict()))

@receiver(post_delete, sender=FeedProfile)
def delete_collections(sender, instance: FeedProfile, **kwargs):
    db = ArangoDBHelper(instance.collection_name, FakeRequest).db
    try:
        graph = db.graph(db.name.split('_database')[0]+'_graph')
        graph.delete_edge_definition(instance.collection_name+'_edge_collection', purge=True)
        graph.delete_vertex_collection(instance.collection_name+'_vertex_collection', purge=True)
    except BaseException as e:
        logging.error(f"cannot delete collection `{instance.collection_name}`: {e}") 
    

class FileImage(models.Model):
    report = models.ForeignKey(File, related_name='images', on_delete=models.CASCADE)
    file = models.ImageField(upload_to=upload_to_func)
    name = models.CharField(max_length=256)

    @property
    def post_id(self):
        return self.report.post_id

class Job(models.Model):
    history4feed_job = models.OneToOneField(h4f_models.Job, on_delete=models.CASCADE, primary_key=True, related_query_name='job_id', related_name="obstracts_job")

    created = models.DateTimeField(auto_now_add=True)
    state = models.CharField(choices=JobState.choices, max_length=20, default=JobState.RETRIEVING)
    processed_items = models.IntegerField(default=0)
    failed_processes = models.IntegerField(default=0)
    feed = models.ForeignKey(FeedProfile, on_delete=models.CASCADE, null=True)
    profile = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True)
    
    @property
    def feed_id(self):
        if not self.feed:
            return None
        return self.feed.id
    
    @property
    def id(self):
        return self.history4feed_job.id
    
    @property
    def item_count(self):
        return self.processed_items + self.failed_processes
    
    @property
    def history4feed_status(self) -> H4FState:
        return self.history4feed_job.state
