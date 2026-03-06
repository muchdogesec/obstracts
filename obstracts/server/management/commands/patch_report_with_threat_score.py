# this script is designed to patch posts with new AI content check data
# docker exec -it container_name bash
# python manage.py patch_post_with_new_data --help #this will show the help

import io
import logging
from django.core.management.base import BaseCommand
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from obstracts.server import models as ob_models
from txt2stix.txt2stix import Txt2StixData
from txt2stix.txt2stix import parse_model
from dogesec_commons.stixifier.stixifier import StixifyProcessor, ReportProperties
from dogesec_commons.objects.helpers import ArangoDBHelper


class Command(BaseCommand):
    help = """
    Patch posts with new AI content check data.
    This command is meant to be run after upgrading to txt2stix v1.4+, which introduced the new `threat_score` field in the `txt2stix_data.content_check`.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stats_lock = Lock()
        self.processed = 0
        self.failed = 0

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
            "--has-incident",
            dest="has_incident",
            action="store_true",
            help="Only process posts that describe incidents (will run AI check)",
        )
        parser.add_argument(
            "--no-incident",
            dest="no_incident",
            action="store_true",
            help="Only process posts that do NOT describe incidents (will set threat_score to 0)",
        )

    def process_file_no_incident(self, file_obj: ob_models.File):
        """Process files that do not describe incident - only update threat_score to 0"""
        try:            
            # Load existing txt2stix_data
            if not file_obj.txt2stix_data:
                self.stdout.write(self.style.WARNING(f"Post {file_obj.post_id}: No txt2stix_data found, skipping"))
                return False
            
            data = Txt2StixData.model_validate(file_obj.txt2stix_data)
            data.content_check.threat_score = 0
            
            file_obj.set_txt2stix_data(data)  # this will also update the content_check field in the database
            self.update_report_confidence(file_obj, confidence=0)
            
            with self.stats_lock:
                self.processed += 1
            
            self.stdout.write(f"Processed post {file_obj.post_id} (feed {file_obj.feed_id}) (no incident)")
            return True
            
        except Exception as e:
            logging.exception("Processing failed for post %s", file_obj.post_id)
            with self.stats_lock:
                self.failed += 1
            return False

    def process_file_with_incident(self, file_obj: ob_models.File):
        """Process files that describe incident - run AI check and update content_check"""
        try:
            post = file_obj.post
            profile = file_obj.profile
            
            if not profile or not profile.ai_content_check_provider:
                self.stdout.write(
                    self.style.WARNING(
                        f"Post {post.id}: No profile or ai_content_check_provider set, skipping"
                    )
                )
                return False
            
            # Get markdown content
            if not file_obj.markdown_file:
                self.stdout.write(self.style.WARNING(f"Post {post.id}: No markdown file found, skipping"))
                return False
            
            markdown_content = file_obj.markdown_file.open().read().decode()
            model = parse_model(profile.ai_content_check_provider)
            describes_incident = model.check_content(markdown_content)
            data = Txt2StixData.model_validate(file_obj.txt2stix_data)
            data.content_check = describes_incident
            file_obj.set_txt2stix_data(data)
            self.update_report_confidence(file_obj, confidence=data.content_check.threat_score)
            
            with self.stats_lock:
                self.processed += 1
            
            self.stdout.write(f"Processed post {post.id} (with incident)")
            return True
            
        except Exception as e:
            logging.exception("Processing failed for post %s", file_obj.post_id)
            with self.stats_lock:
                self.failed += 1
            return False

    def handle(self, *args, **options):
        limit = options.get("limit")
        dry_run = options.get("dry_run")
        has_incident = options.get("has_incident", False)
        no_incident = options.get("no_incident", False)

        if has_incident and no_incident:
            self.stdout.write(
                self.style.ERROR("Cannot specify both --has-incident and --no-incident")
            )
            return

        # Build query
        kwargs = {}
        if options.get("feed_id"):
            kwargs["feed_id__in"] = options["feed_id"]
        if options.get("post_id"):
            kwargs["post__id__in"] = options["post_id"]
        
        qs = ob_models.File.objects.filter(
            txt2stix_data__isnull=False,
            **kwargs
        ).order_by("feed_id", "post__datetime_added")  # order by feed_id and post_id for more consistent processing order
        self.stdout.write(f"Found {qs.count()} files matching feed_id and post_id filters")
        qs = qs.filter(
            txt2stix_data__content_check__threat_score__isnull=True,
        )
        self.stdout.write(f"Found {qs.count()} files with no prior threat_score (eligible for processing)")
        if has_incident:
            qs = qs.filter(txt2stix_data__content_check__describes_incident=True)
            self.stdout.write(f"Found {qs.count()} files that describe incidents (will run AI check)")
        if no_incident:
            qs = qs.filter(txt2stix_data__content_check__describes_incident=False)
            self.stdout.write(f"Found {qs.count()} files that do NOT describe incidents (will set threat_score to 0)")
        f = qs.first()
        matches = list(qs)

        if limit:
            matches = matches[:limit]

        if dry_run:
            self.stdout.write(f"Dry run: {len(matches)} posts match the filter")
            for p in matches:
                self.stdout.write(f"- post {p.post_id} title={p.post.title}|| feed {p.feed_id}, confidence={p.txt2stix_data['content_check'].get('threat_score', 'N/A')}")
            return

        self.stdout.write(f"Processing {len(matches)} posts with up to 12 concurrent workers")
        
        # Process files concurrently
        with ThreadPoolExecutor(max_workers=12) as executor:
            futures = {}
            for file_obj in matches:
                if file_obj.txt2stix_data['content_check']['describes_incident']:
                    futures[executor.submit(self.process_file_with_incident, file_obj)] = file_obj
                else:
                    futures[executor.submit(self.process_file_no_incident, file_obj)] = file_obj
            
            # Wait for all futures to complete
            for future in as_completed(futures):
                file_obj = futures[future]
                try:
                    future.result()
                except Exception as e:
                    logging.exception("Error processing file %s", file_obj.post_id)
                    with self.stats_lock:
                        self.failed += 1
        self.stdout.write(f"Done. processed={self.processed} failed={self.failed}")

    def update_report_confidence(self, file_obj: ob_models.File, confidence):
        arango_helper = ArangoDBHelper(None, None)
        report_id = "report--"+str(file_obj.post_id)
        query = """
        FOR r IN @@collection
        FILTER r.id == @report_id AND r._is_latest == true
        LET updates = COUNT(r.object_refs) > 0 ? @updates : MERGE(@updates, {object_refs: [r.created_by_ref]})
        UPDATE r WITH updates IN @@collection
        """
        bind_vars = {
            "@collection": file_obj.feed.vertex_collection,
            "report_id": report_id,
            "updates": {
                "confidence": confidence
            }
        }
        arango_helper.execute_query(query, bind_vars=bind_vars, paginate=False)