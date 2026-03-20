from django.core.management.base import BaseCommand
from django.conf import settings
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from obstracts.classifier.tasks import run_clustering

# set up logging
import logging
logging.basicConfig()
logging.getLogger(__name__).setLevel(logging.INFO)

class Command(BaseCommand):
    help = "Run HDBSCAN clustering. Use --daemon to run on a recurring cron schedule."

    def add_arguments(self, parser):
        parser.add_argument(
            "--daemon",
            action="store_true",
            default=False,
            help="Run as a blocking daemon that re-clusters on the cron schedule defined by CLASSIFIER_CRON_SCHEDULE.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Force clustering even if no new embeddings have been added since the last run.",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=12,
            help="Number of worker threads to use for concurrent labelling of clusters.",
        )

    def handle(self, *args, **options):
        force = options["force"]
        workers = options["workers"]
        kwargs = {"force": force, "workers": workers}
        if options["daemon"]:
            sched = BlockingScheduler(timezone="UTC")

            @sched.scheduled_job(CronTrigger.from_crontab(settings.CLASSIFIER_CRON_SCHEDULE))
            def scheduled_run_clustering():
                self.stdout.write("Running scheduled clustering...")
                run_clustering.apply(kwargs=kwargs)
                self.stdout.write(self.style.SUCCESS("Scheduled clustering complete."))

            self.stdout.write(
                self.style.SUCCESS(
                    f"Starting scheduler (cron: {settings.CLASSIFIER_CRON_SCHEDULE}). Press Ctrl+C to stop."
                )
            )
            self.stdout.write(f"Next scheduled run at: {sched.get_jobs()[0]}")
            sched.start()
        else:
            self.stdout.write("Running clustering once...")
            job = run_clustering.apply(kwargs=kwargs)
            job.get()  # Wait for completion and raise any exceptions
            self.stdout.write(self.style.SUCCESS("Done."))
