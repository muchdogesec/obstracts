import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

import numpy as np
import openai
import hdbscan

from celery import shared_task
from django.conf import settings

from .models import DocumentEmbedding, Cluster


def _openai_client():
    openai.api_key = os.getenv("OPENAI_API_KEY")
    return openai.Client()


def compute_embedding_for_document(doc: DocumentEmbedding):
    """Fetch a document by id, compute embedding using OpenAI small-3."""
    if not doc.text:
        raise ValueError("Document text is empty, cannot compute embedding")

    client = _openai_client()
    try:
        resp = client.embeddings.create(
            input=doc.text, model="text-embedding-3-small", dimensions=512
        )
        vec = resp.data[0].embedding  # list of floats
        # store as list of floats; `updated_at` is auto-updated by the model
        doc.embedding = vec
        doc.save(update_fields=["embedding", "updated_at"])
        print(f"Saved embedding for doc {doc.pk}")
    except Exception as e:
        print(f"Embedding failed for {doc.pk}: {e}")
        raise


def create_embedding_text(*texts: List[str]) -> str:
    """Create a single string to embed from multiple text fields."""
    # simple concat with separator, could be improved with field weighting or truncation
    texts = [t.strip() for t in texts if t and t.strip()]
    return " | ".join(texts)


@shared_task(bind=True)
def run_clustering(
    self,
    min_cluster_size: int = settings.CLASSIFIER_MIN_CLUSTER_SIZE,
    force: bool = False,
    workers: int = 12,
):
    """Cluster all documents with embeddings, create clusters, and label them."""
    # Only run if new embeddings were added since last cluster
    qs = DocumentEmbedding.objects.exclude(embedding__isnull=True)
    print(f"Found {qs.count()} documents with embeddings for clustering")
    print("cluster count: %d" % Cluster.objects.count())
    last_cluster = Cluster.objects.order_by("-created_at").first()
    print(
        "Starting clustering task. Last cluster created at: %s",
        last_cluster.created_at if last_cluster else "never",
    )
    if not force and last_cluster is not None:
        # Are there any embeddings updated after the last cluster run?
        newer_exists = (
            DocumentEmbedding.objects.exclude(embedding__isnull=True)
            .filter(updated_at__gt=last_cluster.created_at)
            .exists()
        )
        if not newer_exists:
            print(f"No new embeddings since last clustering at {last_cluster.created_at} — skipping.")
            return

    vecs = []
    ids = []
    for d in qs:
        vecs.append(np.array(d.embedding, dtype=float))
        ids.append(d.pk)

    print(f"Clustering {len(vecs)} documents with embeddings")

    if not vecs:
        print("No embeddings available for clustering")
        return

    X = np.vstack(vecs)
    try:
        clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size)
        labels = clusterer.fit_predict(X)
    except Exception as e:
        print(f"HDBSCAN failed: {e}")
        raise

    old_cluster_ids = list(Cluster.objects.values_list("pk", flat=True))

    label_to_members = {}
    for doc_id, label in zip(ids, labels):
        if label == -1:
            continue
        label_to_members.setdefault(int(label), []).append(doc_id)

    # Create clusters and assign members; collect sample texts for concurrent labelling
    pending = []
    for label, member_ids in label_to_members.items():
        cluster = Cluster.objects.create()
        cluster.members.add(*DocumentEmbedding.objects.filter(pk__in=member_ids))
        sample_texts = list(
            DocumentEmbedding.objects.filter(pk__in=member_ids).values_list(
                "text", flat=True
            )[: settings.CLASSIFIER_LABEL_SAMPLE_SIZE]
        )
        pending.append((cluster, sample_texts))

    def label_and_save(cluster, sample_texts):
        label_text = _label_cluster(sample_texts)
        if label_text:
            cluster.label = label_text.get("label", "")
            cluster.description = label_text.get("description", "")
            cluster.save()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(label_and_save, cluster, sample_texts): cluster
            for cluster, sample_texts in pending
        }
        for future in as_completed(futures):
            cluster = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"Labelling failed for cluster {cluster.pk}: {e}")

    # Delete previous clusters only after new ones are in place
    Cluster.objects.filter(pk__in=old_cluster_ids).delete()
    print(f"Clustering complete: {len(label_to_members)} clusters")


def _label_cluster(sample_texts: List[str]) -> dict:
    """Call OpenAI to create a short label and 1-line description for a cluster."""
    client = _openai_client()
    prompt = (
        "You are a helpful assistant. Given the following short excerpts from texts, provide a concise topic label (3 words max) and a one-sentence description describing the common theme.\n"
        "The label and description should be separated by a newline, with the label on the first line.\n"
        "\n\nSample excerpts:\n"
    )
    prompt += "\n".join([f"- {t[:1024]}" for t in sample_texts])
    resp = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.choices[
        0
    ].message.content.strip()  # naive parse: split first line as label if present
    # naive parse: split first line as label if present
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    label = lines[0] if lines else ""
    description = " ".join(lines[1:]) if len(lines) > 1 else ""
    return {"label": label, "description": description}
