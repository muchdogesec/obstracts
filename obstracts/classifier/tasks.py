import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, List

import numpy as np
import openai
import hdbscan
import joblib

from celery import shared_task
from django.conf import settings

from .models import DocumentEmbedding, Cluster


class ClusteringCancelled(Exception):
    pass


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


def run_clustering(
    min_cluster_size: int = settings.CLASSIFIER_MIN_CLUSTER_SIZE,
    force: bool = False,
    workers: int = 12,
    should_cancel=None,
):
    """Cluster all documents with embeddings, create clusters, and label them.

    Full run (no saved model): fits HDBSCAN on all embeddings, saves the model
    and label→cluster-UUID mapping to joblib, then recreates all clusters in DB.

    Incremental run (model already saved): loads the model, runs
    approximate_predict on only the new embeddings (updated since the last
    cluster was created), and adds those embeddings to the appropriate existing
    Cluster objects without touching existing labels or IDs.
    """
    model_path = settings.CLASSIFIER_MODEL_PATH

    full_run = force or not os.path.exists(model_path)

    if should_cancel and should_cancel():
        raise ClusteringCancelled("clustering cancelled before start")

    if full_run:
        _run_full_clustering(model_path, min_cluster_size, workers, should_cancel)
    else:
        _run_incremental_clustering(model_path, workers, should_cancel)


def _run_full_clustering(model_path: str, min_cluster_size: int, workers: int, should_cancel=None):
    """Fit HDBSCAN on all embeddings, persist model, recreate clusters."""
    qs = DocumentEmbedding.objects.exclude(embedding__isnull=True)
    count = qs.count()
    print(f"Full clustering run: {count} documents with embeddings")

    if count == 0:
        print("No embeddings available for clustering — skipping.")
        return

    if should_cancel and should_cancel():
        raise ClusteringCancelled("clustering cancelled before fit")

    vecs = []
    ids = []
    for d in qs:
        vecs.append(np.array(d.embedding, dtype=float))
        ids.append(d.pk)

    X = np.vstack(vecs)
    try:
        clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, prediction_data=True)
        labels = clusterer.fit_predict(X)
    except Exception as e:
        print(f"HDBSCAN failed: {e}")
        raise

    label_to_members: dict[int, list] = {}
    for doc_id, label in zip(ids, labels):
        if label == -1:
            continue
        label_to_members.setdefault(int(label), []).append(doc_id)

    # Snapshot old clusters for deferred deletion
    old_cluster_ids = list(Cluster.objects.values_list("pk", flat=True))

    # Create new Cluster objects; collect samples for concurrent labelling
    label_to_cluster_id: dict[int, str] = {}
    clusters = []
    for label, member_ids in label_to_members.items():
        cluster = new_cluster(member_ids)
        label_to_cluster_id[label] = str(cluster.pk)
        clusters.append(cluster)

    _label_clusters(clusters, workers, should_cancel)

    # Persist the fitted model and label→UUID map
    joblib.dump(
        {"clusterer": clusterer, "label_to_cluster_id": label_to_cluster_id},
        model_path,
    )
    print(f"Saved clusterer to {model_path}")

    # Remove old clusters now that the new ones are fully set up
    Cluster.objects.filter(pk__in=old_cluster_ids).delete()
    print(f"Full clustering complete: {len(label_to_members)} clusters created")

def _label_clusters(clusters: list[Cluster], workers: int, should_cancel=None):
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures: dict[Any, Cluster] = {}
        for cluster in clusters:
            sample_texts = cluster.members.all().values_list("text", flat=True)[: settings.CLASSIFIER_LABEL_SAMPLE_SIZE]
            future = executor.submit(_label_cluster, list(sample_texts))
            futures[future] = cluster
        for future in as_completed(futures):
            if should_cancel and should_cancel():
                executor.shutdown(wait=False, cancel_futures=True)
            cluster = futures[future]
            try:
                result = future.result()
                if result:
                    cluster.label = result.get("label", "")
                    cluster.description = result.get("description", "")
                    cluster.save(update_fields=["label", "description"])
            except Exception as e:
                print(f"Labelling failed for cluster {cluster.pk}: {e}")


def new_cluster(member_ids: list) -> Cluster:
    """Create a new cluster with the given member IDs and return it."""
    cluster = Cluster.objects.create()
    cluster.members.add(*DocumentEmbedding.objects.filter(pk__in=member_ids))
    return cluster

def _run_incremental_clustering(model_path: str, workers: int, should_cancel=None):
    """Assign new embeddings to existing clusters using approximate_predict."""
    last_cluster = Cluster.objects.order_by("-created_at").first()

    new_qs = DocumentEmbedding.objects.exclude(embedding__isnull=True)
    if last_cluster is not None:
        new_qs = new_qs.filter(updated_at__gt=last_cluster.created_at)

    new_count = new_qs.count()
    print(f"Incremental clustering: {new_count} new embeddings since last run")

    if new_count == 0:
        print("No new embeddings — skipping incremental update.")
        return

    if should_cancel and should_cancel():
        raise ClusteringCancelled("clustering cancelled before incremental predict")

    saved = joblib.load(model_path)
    clusterer: hdbscan.HDBSCAN = saved["clusterer"]
    label_to_cluster_id: dict[int, str] = saved["label_to_cluster_id"]

    vecs = []
    docs = []
    for d in new_qs:
        vecs.append(np.array(d.embedding, dtype=float))
        docs.append(d)

    X_new = np.vstack(vecs)
    try:
        labels, _ = hdbscan.approximate_predict(clusterer, X_new)
    except Exception as e:
        print(f"approximate_predict failed: {e}")
        raise

    label_to_new_members: dict[int, list] = {}
    for doc, label in zip(docs, labels):
        if label == -1:
            continue
        label_to_new_members.setdefault(int(label), []).append(doc)

    updated = False
    new_clusters = []
    for label, new_docs in label_to_new_members.items():
        cluster_id = label_to_cluster_id.get(label)
        if cluster_id is None:
            cluster = new_cluster([d.pk for d in new_docs])
            label_to_cluster_id[label] = str(cluster.pk)
            updated = True
            new_clusters.append(cluster)
            print(f"New cluster created for label {label} with {len(new_docs)} members")
        else:
            cluster = Cluster.objects.get(pk=cluster_id)
            cluster.members.add(*new_docs)
            print(f"Added {len(new_docs)} new members to cluster {cluster_id}")

    if new_clusters:
            _label_clusters(new_clusters, workers=workers, should_cancel=should_cancel)

    if updated:
        joblib.dump(
            {"clusterer": clusterer, "label_to_cluster_id": label_to_cluster_id},
            model_path,
        )
        print(f"Updated model saved to {model_path}")

    print(f"Incremental clustering complete: updated {len(label_to_new_members)} clusters")


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
