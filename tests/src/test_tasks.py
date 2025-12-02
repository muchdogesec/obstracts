import copy
import io
from unittest.mock import MagicMock, patch, call
import pytest
import uuid
from obstracts.cjob.tasks import (
    add_pdf_to_post,
    create_pdf_reindex_job,
    download_pdf,
    process_post,
    start_processing,
    reindex_pdf_for_post,
    wait_in_queue,
)
from obstracts.server import models
from history4feed.app import models as h4f_models

from obstracts.server.views import PostOnlyView


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
        patch("obstracts.cjob.tasks.queue_lock", return_value=True) as mock_queue_lock,
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
        h4f_models.FulltextJob.objects.create(
            post_id=post.id,
            job_id=obstracts_job.id,
            status=h4f_models.FullTextState.RETRIEVED,
        )
        post_ids.append(str(post.id))

    with (
        patch("obstracts.cjob.tasks.wait_in_queue.run") as mock_wait_in_queue,
        patch("obstracts.cjob.tasks.process_post.run") as mock_process_post,
        patch(
            "obstracts.cjob.tasks.job_completed_with_error.run"
        ) as mock_job_completed_with_error,
    ):
        start_processing.si(obstracts_job.id).delay()
        mock_wait_in_queue.assert_called_once_with(obstracts_job.id)
        mock_process_post.assert_has_calls(
            [call(obstracts_job.id, post_id) for post_id in post_ids], any_order=True
        )
        mock_job_completed_with_error.assert_called_once_with(obstracts_job.id)


@pytest.mark.django_db
def test_process_post_job__already_cancelled(obstracts_job):
    obstracts_job.cancel()
    post_id = "72e1ad04-8ce9-413d-b620-fe7c75dc0a39"
    process_post.si(obstracts_job.id, post_id).delay()
    obstracts_job.refresh_from_db()
    assert (
        obstracts_job.errors[0]
        == "job cancelled by user for post 72e1ad04-8ce9-413d-b620-fe7c75dc0a39"
    )


@pytest.mark.django_db
def test_process_post_job__fails(obstracts_job):
    obstracts_job.failed_processes = 8
    obstracts_job.save()
    post_id = "72e1ad04-8ce9-413d-b620-fe7c75dc0a39"
    with (
        patch(
            "obstracts.cjob.tasks.StixifyProcessor", side_effect=ValueError
        ) as mock_stixify_processor_cls,
    ):
        process_post.si(obstracts_job.id, post_id).delay()
        obstracts_job.refresh_from_db()
        assert (
            obstracts_job.errors[0]
            == "processing failed for post 72e1ad04-8ce9-413d-b620-fe7c75dc0a39"
        )
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
    obstracts_job.failed_processes = 5
    obstracts_job.save()
    post = h4f_models.Post.objects.get(pk=post_id)
    post.categories.set(
        h4f_models.Category.objects.get_or_create(name=x)[0]
        for x in ("cat1", "cat2", "dog1", "dog2")
    )
    post.save()
    with (
        patch("obstracts.cjob.tasks.StixifyProcessor") as mock_stixify_processor_cls,
        patch(
            "obstracts.cjob.tasks.add_pdf_to_post.run", side_effect=add_pdf_to_post.run
        ) as mock_add_pdf_to_post,
        patch("obstracts.cjob.tasks.download_pdf") as mock_download_pdf,
        patch.object(
            PostOnlyView, "remove_report_objects"
        ) as mock_remove_report_objects,
    ):
        mock_download_pdf.return_value = b"this is a pdf"
        mock_stixify_processor_cls.return_value = fake_stixifier_processor
        process_post.si(obstracts_job.id, post_id).delay()
        obstracts_job.refresh_from_db()
        file = models.File.objects.get(pk=post_id)
        mock_add_pdf_to_post.assert_called_once_with(str(obstracts_job.id), post_id)
        mock_remove_report_objects.assert_called_once_with(
            file
        )  # assert report/post objects removed
        assert file.profile == obstracts_job.profile
        assert file.feed == obstracts_job.feed
        mock_stixify_processor_cls.assert_called_once()
        mock_stixify_processor_cls.return_value.setup.assert_called_once()
        assert mock_stixify_processor_cls.return_value.setup.call_args[0][1] == dict(
            _obstracts_feed_id=str(obstracts_job.feed.id), _obstracts_post_id=post_id
        )
        assert [
            x.removeprefix("tag.")
            for x in mock_stixify_processor_cls.return_value.setup.call_args[0][
                0
            ].labels
        ] == ["cat1", "cat2", "dog1", "dog2"]
        assert file.processed == True
        assert file.summary == fake_stixifier_processor.summary
        assert file.txt2stix_data == {"data": "data is here"}
        assert file.markdown_file.read() == b"Generated MD File"
        assert obstracts_job.failed_processes == 5
        assert obstracts_job.processed_items == 13
        process_stream: io.BytesIO = mock_stixify_processor_cls.call_args[0][0]
        process_stream.seek(0)
        assert process_stream.getvalue() == file.post.description.encode()
        assert file.pdf_file.read() == mock_download_pdf.return_value
        mock_stixify_processor_cls.assert_called_once_with(
            process_stream,
            obstracts_job.profile,
            job_id="72e1ad04-8ce9-413d-b620-fe7c75dc0a39+164716d9-85af-4a81-8f71-9168db3fadf0",
            file2txt_mode="html_article",
            report_id=post_id,
            base_url=file.post.link,
        )


@pytest.mark.django_db
@pytest.mark.parametrize("generate_pdf", [True, False])
def test_process_post_generate_pdf(
    obstracts_job, fake_stixifier_processor, generate_pdf
):
    post_id = "72e1ad04-8ce9-413d-b620-fe7c75dc0a39"
    obstracts_job.profile.generate_pdf = generate_pdf
    obstracts_job.profile.save()

    with (
        patch("obstracts.cjob.tasks.StixifyProcessor") as mock_stixify_processor_cls,
        patch(
            "obstracts.cjob.tasks.add_pdf_to_post.run", side_effect=add_pdf_to_post.run
        ) as mock_add_pdf_to_post,
    ):
        mock_stixify_processor_cls.return_value = fake_stixifier_processor
        process_post.si(obstracts_job.id, post_id).delay()
        assert (
            mock_add_pdf_to_post.called == generate_pdf
        )  # should only be called if generate_pdf == True
        file = models.File.objects.get(pk=post_id)
        assert file.processed == True


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


@pytest.mark.parametrize(
    "consent_setting",
    [
        models.PDFCookieConsentMode.disable_all_js,
        models.PDFCookieConsentMode.remove_cookie_elements,
    ],
)
@pytest.mark.django_db
def test_add_pdf_to_post(obstracts_job, consent_setting):
    post_id = "72e1ad04-8ce9-413d-b620-fe7c75dc0a39"
    feedp = models.FeedProfile.objects.get(
        feed_id=models.File.objects.get(pk=post_id).feed_id
    )
    feedp.pdfshift_cookie_settings = consent_setting
    feedp.save()

    with (patch("obstracts.cjob.tasks.download_pdf") as mock_download_pdf,):
        mock_download_pdf.return_value = b"assume this is a pdf"
        add_pdf_to_post(obstracts_job.id, post_id)
        mock_download_pdf.assert_called_once_with(
            "https://example.blog/3", cookie_consent_mode=consent_setting
        )
        post_file = models.File.objects.get(pk=post_id)
        assert post_file.pdf_file.read() == mock_download_pdf.return_value


@pytest.mark.django_db
def test_add_pdf_to_post__failure(obstracts_job):
    post_id = "72e1ad04-8ce9-413d-b620-fe7c75dc0a39"
    with (patch("obstracts.cjob.tasks.download_pdf") as mock_download_pdf,):
        mock_download_pdf.side_effect = Exception
        add_pdf_to_post(obstracts_job.id, post_id)
        mock_download_pdf.assert_called_once_with(
            "https://example.blog/3",
            cookie_consent_mode=models.PDFCookieConsentMode.disable_all_js,
        )
        obstracts_job.refresh_from_db()
        assert len(obstracts_job.errors) == 1


def test_download_pdf():
    result = download_pdf("https://one.one.one.one/faq/", is_demo=True)
    assert tuple(result[:4]) == (0x25, 0x50, 0x44, 0x46)


@pytest.fixture
def pdf_job(feed_with_posts, stixifier_profile):
    job = models.Job.objects.create(
        feed=feed_with_posts,
        profile=stixifier_profile,
        type=models.JobType.PDF_INDEX,
        id=uuid.uuid4(),
    )
    return job


@pytest.mark.django_db
def test_reindex_pdf_for_post_success(pdf_job):
    post_file = models.File.objects.first()
    post_file.profile.generate_pdf = True
    post_file.profile.save()

    with patch("obstracts.cjob.tasks.download_pdf") as mock_download_pdf:
        mock_download_pdf.return_value = b"pdf content"
        reindex_pdf_for_post.s(pdf_job.id, post_file.pk).delay()

    pdf_job.refresh_from_db()
    post_file.refresh_from_db()

    mock_download_pdf.assert_called_once_with(
        post_file.post.link,
        cookie_consent_mode=models.PDFCookieConsentMode.disable_all_js,
    )
    assert post_file.pdf_file.read() == b"pdf content"
    assert pdf_job.processed_items == 1
    assert pdf_job.failed_processes == 0
    assert not pdf_job.errors
    assert pdf_job.state == models.JobState.PROCESSING


@pytest.mark.django_db
def test_reindex_pdf_for_post_no_generate_pdf(pdf_job, stixifier_profile_no_pdf):
    post_file = models.File.objects.first()
    post_file.profile = stixifier_profile_no_pdf
    post_file.save()

    with patch("obstracts.cjob.tasks.download_pdf") as mock_download_pdf:
        reindex_pdf_for_post.s(pdf_job.id, post_file.pk).delay()

    pdf_job.refresh_from_db()
    mock_download_pdf.assert_not_called()
    assert not post_file.pdf_file
    assert pdf_job.failed_processes == 1
    assert pdf_job.errors == [f"cannot generate pdf for file {post_file.pk}"]


@pytest.mark.django_db
def test_reindex_pdf_for_post_download_fails(pdf_job):
    post_file = models.File.objects.first()
    post_file.profile.generate_pdf = True
    post_file.profile.save()

    with patch(
        "obstracts.cjob.tasks.download_pdf", side_effect=Exception("Download failed")
    ):
        reindex_pdf_for_post.s(pdf_job.id, post_file.pk).delay()

    pdf_job.refresh_from_db()
    assert not post_file.pdf_file
    assert pdf_job.failed_processes == 1
    assert pdf_job.errors == [f"process file to pdf failed for {post_file.pk}"]


@pytest.mark.django_db
def test_reindex_pdf_for_post_job_cancelled(pdf_job):
    post_file = models.File.objects.first()
    pdf_job.cancel()

    with patch("obstracts.cjob.tasks.download_pdf") as mock_download_pdf:
        reindex_pdf_for_post.s(pdf_job.id, post_file.pk).delay()

    mock_download_pdf.assert_not_called()


@pytest.mark.django_db
def test_create_pdf_reindex_job(feed_with_posts):
    with patch("obstracts.cjob.tasks.reindex_pdf_for_post.run") as mock_reindex:
        job = create_pdf_reindex_job(feed_with_posts, models.File.objects.all())
    assert mock_reindex.call_count == 4


@pytest.mark.django_db
def test_create_pdf_reindex_job__skips_no_pdf(
    feed_with_posts, stixifier_profile_no_pdf
):
    post_file = models.File.objects.first()
    post_file.profile = stixifier_profile_no_pdf
    post_file.save()
    with patch("obstracts.cjob.tasks.download_pdf") as mock_download_pdf:
        mock_download_pdf.return_value = b""
        job = create_pdf_reindex_job(feed_with_posts, models.File.objects.all())
    assert mock_download_pdf.call_count == 3
    job.refresh_from_db()
    assert job.failed_processes == 1
    assert job.processed_items == 3


@pytest.mark.django_db
def test_update_vulnerabilities_task_success():
    import uuid
    job = models.Job.objects.create(id=uuid.uuid4(), type=models.JobType.SYNC_VULNERABILITIES, state=models.JobState.PROCESSING)
    with patch("obstracts.cjob.tasks.helpers.run_on_collections") as mock_run:
        # no exception -> should set state to PROCESSED
        mock_run.return_value = None
        from obstracts.cjob.tasks import update_vulnerabilities

        update_vulnerabilities(job.id)
    job.refresh_from_db()
    assert job.state == models.JobState.PROCESSED


@pytest.mark.django_db
def test_update_vulnerabilities_task_failure():
    import uuid
    job = models.Job.objects.create(id=uuid.uuid4(), type=models.JobType.SYNC_VULNERABILITIES, state=models.JobState.PROCESSING)
    with patch("obstracts.cjob.tasks.helpers.run_on_collections", side_effect=Exception("boom")):
        from obstracts.cjob.tasks import update_vulnerabilities

        update_vulnerabilities(job.id)
    job.refresh_from_db()
    assert job.state == models.JobState.PROCESS_FAILED
    assert "boom" in job.errors[0]
