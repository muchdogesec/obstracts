import uuid

from django.db import models
from django.utils import timezone
from pgvector.django import VectorField


class DocumentEmbedding(models.Model):
    """Stores text and its embedding."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    text = models.TextField()
    embedding = VectorField(dimensions=512, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Doc {self.pk} ({len(self.text)} chars)"
    
    def __bool__(self):
        return self.embedding is not None


class Cluster(models.Model):
    """Cluster produced by HDBSCAN with a short label."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    label = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    members = models.ManyToManyField(DocumentEmbedding, related_name="clusters")

    def __str__(self):
        return f"Cluster {self.pk}: {self.label or '<unlabeled>'}"
