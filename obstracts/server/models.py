import json
import logging
import os
from types import SimpleNamespace
import typing
from django.conf import settings
from django.db import models
from django.utils.text import slugify
import txt2stix, txt2stix.extractions
from django.core.exceptions import ValidationError
from dogesec_commons.stixifier.models import Profile
import stix2
from django.utils import timezone
from django.db import transaction

from django.db.models.signals import post_delete
from django.dispatch import receiver
from dogesec_commons.objects.helpers import ArangoDBHelper
from history4feed.app import models as h4f_models
from history4feed.app.models import JobState as H4FState
from django.db.models.signals import post_save
from django.contrib.postgres.fields import ArrayField
from stix2arango.stix2arango import Stix2Arango
from dogesec_commons.objects.db_view_creator import link_one_collection
# Create your models here.
if typing.TYPE_CHECKING:
    from .. import settings


def validate_extractor(types, name):
    extractors = txt2stix.extractions.parse_extraction_config(
            txt2stix.txt2stix.INCLUDES_PATH
        ).values()
    for extractor in extractors:
        if name == extractor.slug and extractor.type in types:
            return True
    raise ValidationError(f"{name} does not exist", 400)


def upload_to_func(instance: 'File|FileImage', filename: str):
    if isinstance(instance, FileImage):
        instance = instance.report
    name_part, _, ext_part = filename.rpartition('.')
    if ext_part and name_part:
        filename = f"{slugify(name_part)}.{ext_part}"
    return os.path.join(str(instance.feed.id), 'posts', str(instance.post_id), filename)

class JobState(models.TextChoices):
    RETRIEVING = "retrieving"
    QUEUED     = "in-queue"
    PROCESSING = "processing"
    PROCESSED  = "processed"
    CANCELLED  = "cancelled"
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
    
    def visible_posts_count(self):
        return self.feed.posts.filter(deleted_manually=False, obstracts_post__processed=True).count()
    
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
    
    @property
    def identity(self):
        return stix2.Identity(
            type="identity",
            spec_version="2.1",
            id=f"identity--{self.id}",
            created_by_ref=f"identity--{settings.STIXIFIER_NAMESPACE}",
            created=self.feed.datetime_added,
            modified=self.feed.datetime_modified or self.feed.datetime_added,
            name=h4f_models.title_as_string(self.feed.title or ""),
            description=h4f_models.title_as_string(self.feed.description or ""),
            contact_information=self.feed.url,
        )
    
    @property
    def identity_dict(self):
        return json.loads(self.identity.serialize())
    
@receiver(post_save, sender=h4f_models.Feed)
def auto_create_feed(sender, instance: h4f_models.Feed, **kwargs):
    feed, created = FeedProfile.objects.update_or_create(feed=instance)
    if created:
        create_collection(feed)


@receiver(post_save, sender=h4f_models.Feed)
def auto_update_identity(sender, instance: h4f_models.Feed, created, **kwargs):
    if not created:
        feed: FeedProfile = instance.obstracts_feed
        update_identities(feed)

def create_collection(feed: FeedProfile):
    s2a = Stix2Arango(database=settings.ARANGODB_DATABASE, collection=feed.collection_name, file='', host_url=settings.ARANGODB_HOST_URL, create_collection=True)
    s2a.run(data=dict(type="bundle", id="bundle--"+str(feed.id), objects=[feed.identity_dict]))
    link_one_collection(s2a.arango.db, settings.ARANGODB_DATABASE_VIEW, feed.vertex_collection)
    link_one_collection(s2a.arango.db, settings.ARANGODB_DATABASE_VIEW, feed.edge_collection)


def update_identities(feed: FeedProfile):
    identity = feed.identity_dict
    identity['_record_modified'] = timezone.now().isoformat().replace('+00:00', 'Z')
    query = """
    FOR doc IN @@vertex_collection
    FILTER doc.id == @identity.id
    UPDATE doc WITH @identity IN @@vertex_collection
    RETURN doc._key
    """
    binds = {
        '@vertex_collection': feed.vertex_collection,
        'identity': identity,
    }

    from django.http.request import HttpRequest
    from rest_framework.request import Request
    helper = ArangoDBHelper(settings.VIEW_NAME, Request(HttpRequest()))
    try:
        updated_keys = helper.execute_query(query, bind_vars=binds, paginate=False)
        logging.info(f"updated {len(updated_keys)} identities for {feed.id}")
    except Exception as e:
        logging.exception("could not update identities")

    
@receiver(post_save, sender=h4f_models.Job)
def start_job(sender, instance: h4f_models.Job, **kwargs):
    from ..cjob import tasks
    if instance.state not in [H4FState.SUCCESS, H4FState.FAILED]:
        return
    job: Job = instance.obstracts_job
    if job.state != JobState.RETRIEVING:
        return
    
    if instance.state == H4FState.SUCCESS:
        tasks.start_processing.delay(instance.id)
    if instance.state == H4FState.FAILED:
        job.update_state(JobState.RETRIEVE_FAILED)
    if instance.is_cancelled():
        job.cancel()
    job.save()


class File(models.Model):
    feed = models.ForeignKey(FeedProfile, on_delete=models.CASCADE, default=None, null=True)
    post = models.OneToOneField(h4f_models.Post, on_delete=models.CASCADE, primary_key=True, related_name="obstracts_post")
    processed = models.BooleanField(default=False)

    markdown_file = models.FileField(upload_to=upload_to_func, null=True)
    pdf_file = models.FileField(upload_to=upload_to_func, null=True)
    summary = models.CharField(max_length=65535, null=True)
    profile = models.ForeignKey(Profile, on_delete=models.PROTECT, default=None, null=True)

    # describe incident
    ai_describes_incident = models.BooleanField(default=None, null=True)
    ai_incident_summary = models.CharField(default=None, max_length=65535, null=True)
    ai_incident_classification = ArrayField(base_field=models.CharField(default=None, max_length=256, null=True), null=True, blank=True)

    txt2stix_data = models.JSONField(default=None, null=True)

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
    errors = ArrayField(base_field=models.CharField(max_length=1024), default=list)

    def is_cancelled(self):
        if self.history4feed_job.is_cancelled():
            self.cancel()
        return self.state == JobState.CANCELLED
    
    def cancel(self):
        self.history4feed_job.cancel()
        self.update_state(JobState.CANCELLED)
        

    @transaction.atomic
    def update_state(self, state):
        obj = self.__class__.objects.select_for_update().get(pk=self.pk)
        if obj.state not in [JobState.RETRIEVING, JobState.PROCESSING, JobState.QUEUED]:
            return obj.state
        obj.state = state
        obj.save()
        self.refresh_from_db()
        return obj.state
    
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
