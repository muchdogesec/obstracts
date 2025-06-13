

import io
from unittest.mock import MagicMock, patch, call
import pytest
from obstracts.cjob.tasks import add_pdf_to_post, download_pdf, job_completed_with_error, process_post, start_processing, wait_in_queue
from obstracts.server import models
from history4feed.app import models as h4f_models
from dogesec_commons.stixifier.stixifier import StixifyProcessor

@pytest.fixture(autouse=True, scope="module")
def celery_eager():
    from history4feed.h4fscripts.celery import app

    app.conf.task_always_eager = True
    app.conf.broker_url = None
    yield
    app.conf.task_always_eager = False


@pytest.mark.django_db
def test_wait_in_queue_already_cancelled(obstracts_job):
    obstracts_job.cancel()
    with (
        patch(
            "obstracts.cjob.tasks.queue_lock", return_value=True
        ) as mock_queue_lock,
    ):
        result = wait_in_queue.si(obstracts_job.id).delay()
        obstracts_job.refresh_from_db()
        assert result.get() == False, obstracts_job.errors
        mock_queue_lock.assert_not_called()


@pytest.mark.django_db
def test_wait_in_queue_retries_until_queue_no_longer_locked(obstracts_job):
    with (
        patch(
            "obstracts.cjob.tasks.queue_lock",
            side_effect=[False, False, True],
        ) as mock_queue_lock,
    ):
        result = wait_in_queue.si(obstracts_job.id).delay()
        obstracts_job.refresh_from_db()
        assert result.get() == True
        assert obstracts_job.state == models.JobState.PROCESSING
        mock_queue_lock.assert_called()
        assert len(mock_queue_lock.call_args_list) == 3

@pytest.mark.django_db
def test_start_processing(obstracts_job):
    obstracts_job.update_state(models.JobState.PROCESSING)
    post_ids = []
    for post in obstracts_job.feed.feed.posts.all():
        h4f_models.FulltextJob.objects.create(post_id=post.id, job_id=obstracts_job.id, status=h4f_models.FullTextState.RETRIEVED)
        post_ids.append(str(post.id))
    
    with (
        patch("obstracts.cjob.tasks.wait_in_queue.run") as mock_wait_in_queue,
        patch("obstracts.cjob.tasks.process_post.run") as mock_process_post,
        patch("obstracts.cjob.tasks.job_completed_with_error.run") as mock_job_completed_with_error,
    ):
        start_processing.si(obstracts_job.id).delay()
        mock_wait_in_queue.assert_called_once_with(obstracts_job.id)
        mock_process_post.assert_has_calls([call(obstracts_job.id, post_id) for post_id in post_ids], any_order=True)
        mock_job_completed_with_error.assert_called_once_with(obstracts_job.id)
        


@pytest.mark.django_db
def test_process_post_job__already_cancelled(obstracts_job):
    obstracts_job.cancel()
    post_id = "72e1ad04-8ce9-413d-b620-fe7c75dc0a39"
    process_post.si(obstracts_job.id, post_id).delay()
    obstracts_job.refresh_from_db()
    assert obstracts_job.errors[0] == "job cancelled by user for post 72e1ad04-8ce9-413d-b620-fe7c75dc0a39"




@pytest.mark.django_db
def test_process_post_job__fails(obstracts_job):
    obstracts_job.failed_processes = 8
    obstracts_job.save()
    post_id = "72e1ad04-8ce9-413d-b620-fe7c75dc0a39"
    with (
        patch("obstracts.cjob.tasks.StixifyProcessor", side_effect=ValueError) as mock_stixify_processor_cls,
    ):
        process_post.si(obstracts_job.id, post_id).delay()
        obstracts_job.refresh_from_db()
        assert obstracts_job.errors[0] == "processing failed for post 72e1ad04-8ce9-413d-b620-fe7c75dc0a39"
        assert obstracts_job.failed_processes == 9

@pytest.fixture
def fake_stixifier_processor():
    mocked_processor = MagicMock()
    mocked_processor.summary = "Summarized post"
    mocked_processor.md_file.open.return_value = io.BytesIO(b"Generated MD File")
    mocked_processor.incident = None
    mocked_processor.txt2stix_data.model_dump.return_value = {"data": "data is here"}
    return mocked_processor
    
@pytest.mark.django_db
def test_process_post_job(obstracts_job, fake_stixifier_processor):
    post_id = "72e1ad04-8ce9-413d-b620-fe7c75dc0a39"
    obstracts_job.processed_items = 12
    obstracts_job.save()

    with (
        patch("obstracts.cjob.tasks.StixifyProcessor") as mock_stixify_processor_cls,
        patch("obstracts.cjob.tasks.add_pdf_to_post") as mock_add_pdf_to_post,
    ):
        mock_stixify_processor_cls.return_value = fake_stixifier_processor
        process_post.si(obstracts_job.id, post_id).delay()
        obstracts_job.refresh_from_db()
        file = models.File.objects.get(pk=post_id)
        mock_add_pdf_to_post.assert_called_once_with(str(obstracts_job.id), post_id)
        assert file.profile == obstracts_job.profile
        assert file.feed == obstracts_job.feed
        mock_stixify_processor_cls.assert_called_once()
        mock_stixify_processor_cls.return_value.setup.assert_called_once()
        assert mock_stixify_processor_cls.return_value.setup.call_args[0][1] == dict(_obstracts_feed_id=str(obstracts_job.feed.id), _obstracts_post_id=post_id)
        assert file.processed == True
        assert file.summary == fake_stixifier_processor.summary
        assert file.txt2stix_data == {"data": "data is here"}
        assert file.markdown_file.read() == b"Generated MD File"
        assert obstracts_job.processed_items == 13
        process_stream: io.BytesIO = mock_stixify_processor_cls.call_args[0][0]
        process_stream.seek(0)
        assert process_stream.getvalue() == file.post.description.encode()
        mock_stixify_processor_cls.assert_called_once_with(
            process_stream,
            obstracts_job.profile,
            job_id='72e1ad04-8ce9-413d-b620-fe7c75dc0a39+164716d9-85af-4a81-8f71-9168db3fadf0',
            file2txt_mode="html_article",
            report_id=post_id,
            base_url=file.post.link,
        )

@pytest.mark.django_db
def test_process_post_with_incident(obstracts_job, fake_stixifier_processor):
    post_id = "72e1ad04-8ce9-413d-b620-fe7c75dc0a39"
    obstracts_job.processed_items = 12
    obstracts_job.save()

    incident = fake_stixifier_processor.incident = MagicMock()
    incident.describes_incident = True
    incident.explanation = "some explanation"
    incident.incident_classification = []

    with (
        patch("obstracts.cjob.tasks.StixifyProcessor") as mock_stixify_processor_cls,
    ):
        mock_stixify_processor_cls.return_value = fake_stixifier_processor
        process_post.si(obstracts_job.id, post_id).delay()
        file = models.File.objects.get(pk=post_id)
        assert file.ai_describes_incident == incident.describes_incident
        assert file.ai_incident_summary == incident.explanation
        assert file.ai_incident_classification == incident.incident_classification


@pytest.mark.django_db
def test_add_pdf_to_post(obstracts_job):
    post_id = "72e1ad04-8ce9-413d-b620-fe7c75dc0a39"
    with (
        patch("obstracts.cjob.tasks.download_pdf") as mock_download_pdf,
    ):
        mock_download_pdf.return_value = b"assume this is a pdf"
        add_pdf_to_post(obstracts_job.id, post_id)
        mock_download_pdf.assert_called_once_with("https://example.blog/3")
        post_file = models.File.objects.get(pk=post_id)
        assert post_file.pdf_file.read() == mock_download_pdf.return_value


@pytest.mark.django_db
def test_add_pdf_to_post__failure(obstracts_job):
    post_id = "72e1ad04-8ce9-413d-b620-fe7c75dc0a39"
    with (
        patch("obstracts.cjob.tasks.download_pdf") as mock_download_pdf,
    ):
        mock_download_pdf.side_effect = Exception
        add_pdf_to_post(obstracts_job.id, post_id)
        mock_download_pdf.assert_called_once_with("https://example.blog/3")
        obstracts_job.refresh_from_db()
        assert len(obstracts_job.errors) == 1

@pytest.mark.django_db
def test_download_pdf():
    result = download_pdf("https://example.com/")
    assert tuple(result[:4]) == (0x25,0x50,0x44,0x46)
