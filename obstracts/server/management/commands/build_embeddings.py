import uuid

from django.core.management.base import BaseCommand

from obstracts.cjob import tasks as cjob_tasks
from obstracts.server import models


class Command(BaseCommand):
    help = "Build embeddings for topic classification within a tracked Job context."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Force regeneration of embeddings even when they already exist.",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=12,
            help="Number of worker threads to use for embedding creation.",
        )
        parser.add_argument(
            "--include-non-incident",
            action="store_true",
            help=(
                "Also include files where ai_describes_incident is false. "
                "This will create embeddings for all files, which may be desirable for broader topic classification but will increase processing time and resource usage."
            ),
        )

    def handle(self, *args, **options):
        force = options["force"]
        workers = options["workers"]
        include_non_incident = options["include_non_incident"]

        job = models.Job.objects.create(
            id=uuid.uuid4(),
            type=models.JobType.BUILD_EMBEDDINGS,
            state=models.JobState.PROCESSING,
        )

        self.stdout.write(f"Running embedding build for job {job.id}...")
        cjob_tasks.run_topic_embeddings_job(
            job.id,
            force=force,
            workers=workers,
            include_non_incident=include_non_incident,
        )
        job.refresh_from_db()
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. job={job.id} state={job.state} processed={job.processed_items} failed={job.failed_processes}"
            )
        )
