import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest
from django.utils import timezone

from obstracts.classifier.models import Cluster, DocumentEmbedding
from obstracts.classifier.tasks import (
    _label_cluster,
    _label_clusters,
    _run_full_clustering,
    _run_incremental_clustering,
    compute_embedding_for_document,
    create_embedding_text,
    new_cluster,
    run_clustering,
)
import obstracts.classifier.tasks

# ── constants ──────────────────────────────────────────────────────────────────

VEC1 = [1.0] + [0.0] * 511
VEC2 = [0.0, 1.0] + [0.0] * 510
VEC3 = [0.0, 0.0, 1.0] + [0.0] * 509

EMB1_ID = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
EMB2_ID = uuid.UUID("cccccccc-0000-0000-0000-000000000002")
EMB3_ID = uuid.UUID("cccccccc-0000-0000-0000-000000000003")


# ── celery eager fixture ───────────────────────────────────────────────────────


@pytest.fixture(autouse=True, scope="module")
def celery_eager():
    from obstracts.cjob.celery import app

    app.conf.task_always_eager = True
    app.conf.broker_url = None
    yield
    app.conf.task_always_eager = False


# ── shared fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def embeddings():
    emb1 = DocumentEmbedding.objects.create(
        id=EMB1_ID, text="Article about malware campaigns", embedding=VEC1
    )
    emb2 = DocumentEmbedding.objects.create(
        id=EMB2_ID, text="Ransomware analysis deep dive", embedding=VEC2
    )
    emb3 = DocumentEmbedding.objects.create(
        id=EMB3_ID, text="APT group targeting finance sector", embedding=VEC3
    )
    return emb1, emb2, emb3


# ── create_embedding_text ──────────────────────────────────────────────────────


def test_create_embedding_text_joins_parts():
    assert create_embedding_text("hello", "world") == "hello | world"
    assert create_embedding_text("  hello  ", "  world  ") == "hello | world"
    assert create_embedding_text("hello", "", "  ", "world") == "hello | world"
    assert create_embedding_text("only") == "only"
    assert create_embedding_text("", "  ") == ""


# ── compute_embedding_for_document ────────────────────────────────────────────


@pytest.mark.django_db
def test_compute_embedding_saves_vector(embeddings):
    emb1, _, _ = embeddings
    emb1.embedding = None
    emb1.save(update_fields=["embedding"])

    mock_client = MagicMock()
    mock_client.embeddings.create.return_value.data = [MagicMock(embedding=VEC1)]

    with patch("obstracts.classifier.tasks._openai_client", return_value=mock_client):
        compute_embedding_for_document(emb1)

    emb1.refresh_from_db()
    assert emb1.embedding is not None
    mock_client.embeddings.create.assert_called_once_with(
        input=emb1.text, model="text-embedding-3-small", dimensions=512
    )


@pytest.mark.django_db
def test_compute_embedding_raises_on_empty_text(embeddings):
    emb1, _, _ = embeddings
    emb1.text = ""
    with pytest.raises(ValueError, match="empty"):
        compute_embedding_for_document(emb1)


@pytest.mark.django_db
def test_compute_embedding_reraises_openai_error(embeddings):
    emb1, _, _ = embeddings
    mock_client = MagicMock()
    mock_client.embeddings.create.side_effect = RuntimeError("API down")

    with patch("obstracts.classifier.tasks._openai_client", return_value=mock_client):
        with pytest.raises(RuntimeError, match="API down"):
            compute_embedding_for_document(emb1)


# ── new_cluster ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_new_cluster_creates_with_members(embeddings):
    emb1, emb2, _ = embeddings
    cluster = new_cluster([emb1.pk, emb2.pk])
    assert Cluster.objects.filter(pk=cluster.pk).exists()
    assert set(cluster.members.values_list("pk", flat=True)) == {emb1.pk, emb2.pk}


@pytest.mark.django_db
def test_new_cluster_empty_members():
    cluster = new_cluster([])
    assert Cluster.objects.filter(pk=cluster.pk).exists()
    assert cluster.members.count() == 0


# ── _label_cluster ─────────────────────────────────────────────────────────────


def test_label_cluster_parses_label_and_description():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices = [
        MagicMock(
            message=MagicMock(
                content="Cyber Threats\nIran-linked ops targeting government agencies."
            )
        )
    ]

    with patch("obstracts.classifier.tasks._openai_client", return_value=mock_client):
        result = _label_cluster(["text1", "text2"])

    assert result["label"] == "Cyber Threats"
    assert result["description"] == "Iran-linked ops targeting government agencies."


def test_label_cluster_single_line_response():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content="LabelOnly"))
    ]

    with patch("obstracts.classifier.tasks._openai_client", return_value=mock_client):
        result = _label_cluster(["text"])

    assert result["label"] == "LabelOnly"
    assert result["description"] == ""


# ── _label_clusters ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_label_clusters_sets_label_and_description(embeddings, monkeypatch):
    emb1, emb2, _ = embeddings
    cluster1 = new_cluster([emb1.pk])
    cluster2 = new_cluster([emb2.pk])

    def fake_label(texts):
        return {"label": "Topic "+texts[0], "description": "A description."}
    with patch("obstracts.classifier.tasks._label_cluster", side_effect=fake_label) as mock_label_cluster:
        _label_clusters([cluster1, cluster2], workers=2)

    cluster1.refresh_from_db()
    cluster2.refresh_from_db()
    mock_label_cluster.assert_has_calls([
        call([emb1.text]),
        call([emb2.text]),
    ], any_order=True)
    assert cluster1.label == "Topic " + emb1.text  # each cluster gets same label but different description
    assert cluster2.label == "Topic " + emb2.text
    assert cluster1.description == "A description."


@pytest.mark.django_db
def test_label_clusters_handles_per_cluster_error_gracefully(embeddings):
    emb1, _, _ = embeddings
    cluster = new_cluster([emb1.pk])

    with patch("obstracts.classifier.tasks._label_cluster", side_effect=RuntimeError("fail")):
        _label_clusters([cluster], workers=1)  # must not raise

    cluster.refresh_from_db()
    assert cluster.label == ""  # not modified because exception was raised


# ── _run_full_clustering ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_run_full_clustering_skips_when_no_embeddings(tmp_path):
    model_path = str(tmp_path / "model.joblib")
    with patch("obstracts.classifier.tasks.joblib.dump") as mock_dump:
        _run_full_clustering(model_path, min_cluster_size=2, workers=2)
    mock_dump.assert_not_called()


@pytest.mark.django_db
def test_run_full_clustering_creates_clusters_and_saves_model(embeddings, tmp_path):
    model_path = str(tmp_path / "model.joblib")
    mock_clusterer = MagicMock()
    mock_clusterer.fit_predict.return_value = np.array([0, 0, 1])

    with (
        patch("obstracts.classifier.tasks.hdbscan.HDBSCAN", return_value=mock_clusterer),
        patch("obstracts.classifier.tasks._label_clusters"),
        patch("obstracts.classifier.tasks.joblib.dump") as mock_dump,
    ):
        _run_full_clustering(model_path, min_cluster_size=2, workers=2)

    assert Cluster.objects.count() == 2
    mock_dump.assert_called_once()
    saved = mock_dump.call_args[0][0]
    assert "clusterer" in saved
    assert set(saved["label_to_cluster_id"].keys()) == {0, 1}


@pytest.mark.django_db
def test_run_full_clustering_calls_label_clusters_with_new_clusters(embeddings, tmp_path):
    model_path = str(tmp_path / "model.joblib")
    mock_clusterer = MagicMock()
    mock_clusterer.fit_predict.return_value = np.array([0, 0, 1])

    with (
        patch("obstracts.classifier.tasks.hdbscan.HDBSCAN", return_value=mock_clusterer),
        patch("obstracts.classifier.tasks._label_clusters") as mock_label,
        patch("obstracts.classifier.tasks.joblib.dump"),
    ):
        _run_full_clustering(model_path, min_cluster_size=2, workers=2)

    mock_label.assert_called_once()
    clusters_arg, workers_arg, cancel_arg = mock_label.call_args[0]
    assert len(clusters_arg) == 2
    assert workers_arg == 2
    assert cancel_arg is None


@pytest.mark.django_db
def test_run_full_clustering_deletes_old_clusters(embeddings, tmp_path):
    model_path = str(tmp_path / "model.joblib")
    old_cluster = Cluster.objects.create(label="old")
    mock_clusterer = MagicMock()
    mock_clusterer.fit_predict.return_value = np.array([0, 0, 1])

    with (
        patch("obstracts.classifier.tasks.hdbscan.HDBSCAN", return_value=mock_clusterer),
        patch("obstracts.classifier.tasks._label_clusters"),
        patch("obstracts.classifier.tasks.joblib.dump"),
    ):
        _run_full_clustering(model_path, min_cluster_size=2, workers=2)

    assert not Cluster.objects.filter(pk=old_cluster.pk).exists()


@pytest.mark.django_db
def test_run_full_clustering_noise_label_ignored(embeddings, tmp_path):
    model_path = str(tmp_path / "model.joblib")
    mock_clusterer = MagicMock()
    mock_clusterer.fit_predict.return_value = np.array([-1, -1, -1])

    with (
        patch("obstracts.classifier.tasks.hdbscan.HDBSCAN", return_value=mock_clusterer),
        patch("obstracts.classifier.tasks._label_clusters"),
        patch("obstracts.classifier.tasks.joblib.dump") as mock_dump,
    ):
        _run_full_clustering(model_path, min_cluster_size=2, workers=2)

    assert Cluster.objects.count() == 0
    saved = mock_dump.call_args[0][0]
    assert saved["label_to_cluster_id"] == {}


# ── _run_incremental_clustering ───────────────────────────────────────────────


@pytest.mark.django_db
def test_run_incremental_skips_when_no_new_embeddings(tmp_path):
    model_path = str(tmp_path / "model.joblib")
    # Cluster created in the future → its created_at > any embedding's updated_at
    future = timezone.now() + timedelta(hours=1)
    Cluster.objects.create(label="existing", created_at=future)
    DocumentEmbedding.objects.create(id=EMB1_ID, text="old text", embedding=VEC1)

    with patch("obstracts.classifier.tasks.joblib.load") as mock_load:
        _run_incremental_clustering(model_path, workers=2)

    mock_load.assert_not_called()


@pytest.mark.django_db
def test_run_incremental_adds_members_to_existing_clusters(embeddings, tmp_path):
    emb1, emb2, emb3 = embeddings
    model_path = str(tmp_path / "model.joblib")

    # Cluster created in the past → all embeddings are "new"
    cluster_id = str(uuid.uuid4())
    past = timezone.now() - timedelta(hours=1)
    Cluster.objects.create(id=cluster_id, label="Malware", created_at=past)

    saved_model = {
        "clusterer": MagicMock(),
        "label_to_cluster_id": {0: cluster_id},
    }

    with (
        patch("obstracts.classifier.tasks.joblib.load", return_value=saved_model),
        patch(
            "obstracts.classifier.tasks.hdbscan.approximate_predict",
            return_value=(np.array([0, 0, 0]), None),
        ),
        patch("obstracts.classifier.tasks.joblib.dump") as mock_dump,
        patch("obstracts.classifier.tasks._label_clusters"),
    ):
        _run_incremental_clustering(model_path, workers=2)

    cluster = Cluster.objects.get(pk=cluster_id)
    assert cluster.members.count() == 3
    # No new clusters were created → joblib not re-saved
    mock_dump.assert_not_called()


@pytest.mark.django_db
def test_run_incremental_creates_new_cluster_for_unknown_label(embeddings, tmp_path):
    emb1, emb2, emb3 = embeddings
    model_path = str(tmp_path / "model.joblib")

    cluster_id = str(uuid.uuid4())
    past = timezone.now() - timedelta(hours=1)
    Cluster.objects.create(id=cluster_id, label="Malware", created_at=past)

    saved_model = {
        "clusterer": MagicMock(),
        "label_to_cluster_id": {0: cluster_id},
    }

    with (
        patch("obstracts.classifier.tasks.joblib.load", return_value=saved_model),
        # emb1 → existing cluster 0; emb2 + emb3 → new label 1
        patch(
            "obstracts.classifier.tasks.hdbscan.approximate_predict",
            return_value=(np.array([0, 1, 1]), None),
        ),
        patch("obstracts.classifier.tasks.joblib.dump") as mock_dump,
        patch("obstracts.classifier.tasks._label_clusters") as mock_label,
    ):
        _run_incremental_clustering(model_path, workers=2)

    assert Cluster.objects.count() == 2
    # Joblib updated with new label→uuid mapping
    mock_dump.assert_called_once()
    updated_model = mock_dump.call_args[0][0]
    assert 1 in updated_model["label_to_cluster_id"]
    # Only the new cluster is labelled
    mock_label.assert_called_once()
    new_clusters_arg = mock_label.call_args[0][0]
    assert len(new_clusters_arg) == 1


@pytest.mark.django_db
def test_run_incremental_skips_noise_embeddings(embeddings, tmp_path):
    emb1, emb2, emb3 = embeddings
    model_path = str(tmp_path / "model.joblib")

    saved_model = {"clusterer": MagicMock(), "label_to_cluster_id": {}}

    with (
        patch("obstracts.classifier.tasks.joblib.load", return_value=saved_model),
        patch(
            "obstracts.classifier.tasks.hdbscan.approximate_predict",
            return_value=(np.array([-1, -1, -1]), None),
        ),
        patch("obstracts.classifier.tasks.joblib.dump") as mock_dump,
    ):
        _run_incremental_clustering(model_path, workers=2)

    assert Cluster.objects.count() == 0
    mock_dump.assert_not_called()


# ── run_clustering dispatch ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_run_clustering_dispatches_full_when_no_model(tmp_path):
    model_path = str(tmp_path / "model.joblib")

    with (
        patch("obstracts.classifier.tasks.settings.CLASSIFIER_MODEL_PATH", model_path),
        patch("obstracts.classifier.tasks._run_full_clustering") as mock_full,
        patch("obstracts.classifier.tasks._run_incremental_clustering") as mock_inc,
    ):
        run_clustering(min_cluster_size=5, force=False, workers=2)

    mock_full.assert_called_once_with(model_path, 5, 2, None)
    mock_inc.assert_not_called()


@pytest.mark.django_db
def test_run_clustering_dispatches_incremental_when_model_exists(tmp_path):
    model_path = str(tmp_path / "model.joblib")
    open(model_path, "w").close()

    with (
        patch("obstracts.classifier.tasks.settings.CLASSIFIER_MODEL_PATH", model_path),
        patch("obstracts.classifier.tasks._run_full_clustering") as mock_full,
        patch("obstracts.classifier.tasks._run_incremental_clustering") as mock_inc,
    ):
        run_clustering(min_cluster_size=5, force=False, workers=2)

    mock_inc.assert_called_once_with(model_path, 2, None)
    mock_full.assert_not_called()


@pytest.mark.django_db
def test_run_clustering_force_dispatches_full_even_with_existing_model(tmp_path):
    model_path = str(tmp_path / "model.joblib")
    open(model_path, "w").close()

    with (
        patch("obstracts.classifier.tasks.settings.CLASSIFIER_MODEL_PATH", model_path),
        patch("obstracts.classifier.tasks._run_full_clustering") as mock_full,
        patch("obstracts.classifier.tasks._run_incremental_clustering") as mock_inc,
    ):
        run_clustering(min_cluster_size=5, force=True, workers=2)

    mock_full.assert_called_once_with(model_path, 5, 2, None)
    mock_inc.assert_not_called()
