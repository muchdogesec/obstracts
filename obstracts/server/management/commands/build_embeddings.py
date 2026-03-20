from django.core.management.base import BaseCommand
from concurrent.futures import ThreadPoolExecutor, as_completed

from obstracts.server import models

WORKERS = 25


class Command(BaseCommand):
    help = (
        "Build embeddings for visible, processed posts where ai_describes_incident=True. "
        "By default skips posts that already have an embedding."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Recompute embeddings even for posts that already have one.",
        )
        parser.add_argument(
            "--feeds",
            nargs="+",
            metavar="FEED_ID",
            default=None,
            help="Limit to one or more feed IDs (space-separated UUIDs).",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=WORKERS,
            help=f"Number of worker threads to use for concurrent embedding (default: {WORKERS}).",
        )

    def handle(self, *args, **options):
        force = options["force"]
        workers = options["workers"]
        feed_ids = options["feeds"]

        qs = models.File.objects.filter(
            processed=True,
            ai_describes_incident=True,
        ).select_related("post", "feed")
        total_eligible = qs.count()

        if feed_ids:
            qs = qs.filter(feed__feed__id__in=feed_ids)

        if not force:
            qs = qs.filter(embedding__isnull=True)

        total = qs.count()
        if total == 0:
            self.stdout.write(f"All {total_eligible} eligible posts already have embeddings.")
            self.stdout.write("No posts to process.")
            return

        self.stdout.write(f"Building embeddings for {total} post(s) out of {total_eligible} eligible...")
        ok = 0
        failed = 0

        files = list(qs)

        def process(file):
            file.create_embedding(force=force)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(process, file): file for file in files}
            for future in as_completed(futures):
                file = futures[future]
                try:
                    future.result()
                    ok += 1
                except Exception as exc:
                    self.stderr.write(f"  FAILED post {file.post_id}: {exc}")
                    failed += 1
                percent = (ok + failed) / total * 100
                self.stdout.write(f"{ok + failed} of {total} processed [{percent:.2f}%].")
                

        self.stdout.write(
            self.style.SUCCESS(f"Done: {ok} succeeded, {failed} failed.")
        )
