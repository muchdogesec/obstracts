# this script is designed to reindex extractions identified in data.json without triggering more calls to an AI. Useful when extractions have failed during lookup to remote sources (e.g. Vulmatch)
# docker exec -it container_name bash
# python manage.py reprocess_posts --help #this will show the help

import logging
import time
from itertools import groupby
from typing import Iterator
from uuid import UUID
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from obstracts.server import models as ob_models
from obstracts.server.models import h4f_models
from obstracts.cjob import tasks as cjob_tasks


class Command(BaseCommand):
    help = "Reprocess posts matching a user-provided filter using create_reprocessing_job. Creates Job entries and waits for completion."
    TERMINAL_JOB_STATES = {
        ob_models.JobState.PROCESSED,
        ob_models.JobState.PROCESS_FAILED,
        ob_models.JobState.RETRIEVE_FAILED,
        ob_models.JobState.CANCELLED,
    }

    @staticmethod
    def _chunked(items: list[ob_models.File], size: int) -> Iterator[list[ob_models.File]]:
        for start in range(0, len(items), size):
            yield items[start:start + size]

    def _iter_feed_batches(
        self,
        files: list[ob_models.File],
        posts_per_job: int,
    ) -> Iterator[tuple[ob_models.FeedProfile, UUID, list[h4f_models.Post]]]:
        for _, feed_group in groupby(files, key=lambda file_obj: (file_obj.feed_id, file_obj.profile_id)):
            feed_files = list(feed_group)
            for batch in self._chunked(feed_files, posts_per_job):
                yield batch[0].feed, batch[0].profile_id, [p.post for p in batch]

    def _wait_for_job_completion(self, job: ob_models.Job, poll_seconds: float = 1.0) -> ob_models.Job:
        while True:
            job.refresh_from_db()
            if job.state in self.TERMINAL_JOB_STATES:
                return job
            time.sleep(poll_seconds)

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            dest="limit",
            type=int,
            default=None,
            help="Maximum number of posts to process",
        )
        parser.add_argument(
            "--dry-run",
            dest="dry_run",
            action="store_true",
            help="Only show which posts would be processed",
        )
        parser.add_argument(
            "--feed_id",
            help="Only run for posts under these feed_ids",
            nargs="+",
            default=None,
        )
        parser.add_argument("--post_id", help="Only run for these post_ids", nargs="+")
        parser.add_argument(
            "--posts-per-job",
            dest="posts_per_job",
            type=int,
            default=100,
            help="Maximum number of posts submitted in each reprocessing job",
        )
        parser.add_argument(
            "--keep-jobs",
            dest="discard_jobs",
            action="store_false",
            default=True,
            help="Keep job entries after completion",
        )
        
        # Mutually exclusive group for processing mode
        mode_group = parser.add_mutually_exclusive_group(required=True)
        mode_group.add_argument(
            "--only-processed",
            dest="only_processed",
            action="store_true",
            help="Only reprocess posts with existing txt2stix_data (skip_extraction=True)",
        )
        mode_group.add_argument(
            "--only-empty",
            dest="only_empty",
            action="store_true",
            help="Only process posts with fewer than 4 object_values (skip_extraction=False)",
        )

    def handle(self, *args, **options):
        limit = options.get("limit")
        dry_run = options.get("dry_run")
        discard_jobs = options['discard_jobs']
        posts_per_job = options['posts_per_job']
        only_processed = options['only_processed']
        only_empty = options['only_empty']

        if posts_per_job <= 0:
            raise CommandError("--posts-per-job must be greater than 0")
        
        # Determine skip_extraction based on mode
        skip_extraction = True  # default
        if only_empty:
            skip_extraction = False

        kwargs = {}
        if options.get("feed_id"):
            kwargs["feed_id__in"] = options["feed_id"]
        if options.get("post_id"):
            kwargs["post__id__in"] = options["post_id"]
        
        # Build queryset based on mode
        qs = ob_models.File.objects.filter(**kwargs)
        
        if only_processed:
            # Filter for posts with existing txt2stix_data
            qs = qs.filter(txt2stix_data__isnull=False)
        elif only_empty:
            # Filter for posts with fewer than 4 object_values
            qs = qs.annotate(object_count=Count('object_values')).filter(object_count__lte=2)
        
        qs = qs.select_related('post', 'feed').order_by('feed_id', 'post__pubdate')
        if limit:
            qs = qs[:limit]
        matches: list[ob_models.File] = list(qs)

        if dry_run:
            self.stdout.write(f"Dry run: {len(matches)} posts match the filter")
            for p in matches:
                self.stdout.write(f"- post {p.feed_id}/{p.post_id} title={p.post.title}")
            batch_count = sum(1 for _ in self._iter_feed_batches(matches, posts_per_job))
            self.stdout.write(
                f"Dry run batching: {batch_count} jobs at up to {posts_per_job} posts per job"
            )
            self.stdout.write(f"Dry run complete. {len(matches)} posts would be processed.")
            return

        self.stdout.write(f"Processing {len(matches)} posts")
        processed = 0
        failed = 0
        for feed, profile_id, posts in self._iter_feed_batches(matches, posts_per_job):
            try:
                # Create one reprocessing job for each feed batch.
                _, job = cjob_tasks.create_reprocessing_job(
                    feed=feed,
                    posts=posts,
                    options={
                        'profile_id': str(profile_id) if profile_id else None,
                        'skip_extraction': skip_extraction,
                    }
                )
                
                self.stdout.write(
                    f"Created job {job.id} for feed {feed.id} ({len(posts)} posts), waiting for completion..."
                )
                
                # Wait for job state to reach a terminal state in DB.
                self._wait_for_job_completion(job)
                
                # Check job status
                job.refresh_from_db()
                job_processed = min(job.processed_items, len(posts))
                if job_processed > 0:
                    processed += job_processed
                    self.stdout.write(
                        f"✓ Processed {job_processed}/{len(posts)} posts for feed {feed.id}"
                    )
                else:
                    self.stdout.write(f"✗ Failed to process posts for feed {feed.id}: {job.errors}")

                failed += max(len(posts) - job_processed, 0)
                
                # Discard job if requested
                if discard_jobs:
                    job.delete()
                    self.stdout.write(f"  Deleted job {job.id}")
                    
            except Exception:
                logging.exception("processing failed for feed %s", feed.id)
                failed += len(posts)

        self.stdout.write(f"Done. processed={processed} failed={failed}")
