from datetime import timedelta
import itertools
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from obstracts.server import models
from history4feed.app import models as h4f_models


class Command(BaseCommand):
    help = "Atomically purge all old jobs older than --days (defaults to 30)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Purge jobs older than this number of days. Defaults to 30.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        cutoff = timezone.now() - timedelta(days=days)

        # Identify obstracts jobs older than the cutoff
        obs_jobs_qs = models.Job.objects.filter(created__lt=cutoff)
        count = obs_jobs_qs.count()

        if count == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"No jobs older than {days} days found (cutoff: {cutoff})."
                )
            )
            return

        self.stdout.write(
            self.style.WARNING(
                f"Found {count} jobs older than {days} days. Starting purge..."
            )
        )

        with transaction.atomic():
            # Get IDs for related history4feed jobs to ensure library data is also cleaned up
            h4f_job_ids = obs_jobs_qs.filter(history4feed_job__isnull=False).values(
                    "history4feed_job_id"
                )

            # 1. Delete history4feed jobs. This cascades to delete the obstracts.Job records.
            _, counts = h4f_models.Job.objects.filter(id__in=h4f_job_ids).delete()

            # 2. Delete remaining obstracts jobs (those without history4feed counterparts)
            _, counts2 = models.Job.objects.filter(created__lt=cutoff).delete()

            total_removed = 0
            all_keys = set(itertools.chain(counts.keys(), counts2.keys()))
            for key in sorted(all_keys):
                deleted_count = counts.get(key, 0) + counts2.get(key, 0)
                self.stdout.write(
                    f"  - {key}: " + self.style.SUCCESS(str(deleted_count))
                )
                total_removed += deleted_count
                
        self.stdout.write(
            self.style.SUCCESS("Successfully purged ")
            + self.style.WARNING(total_removed)
            + self.style.SUCCESS(" total records across all related models.")
        )
