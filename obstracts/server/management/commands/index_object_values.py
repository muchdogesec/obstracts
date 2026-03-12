"""
Management command to index existing STIX objects from ArangoDB into ObjectValue table.

This command retrieves all objects for each post from each feed's ArangoDB collection
and processes them through the process_uploaded_objects_hook to populate the ObjectValue table.

Usage:
    python manage.py index_object_values
    python manage.py index_object_values --feed-id <uuid>
    python manage.py index_object_values --post-id <uuid>
    python manage.py index_object_values --dry-run
"""

import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from arango import ArangoClient

from obstracts.server.models import FeedProfile, File
from obstracts.server.values.values import process_uploaded_objects_hook


logger = logging.getLogger(__name__)


def validate_post_id(value):
    File.objects.get(pk=value)  # Will raise DoesNotExist if invalid
    return value


def validate_feed_id(value):
    FeedProfile.objects.get(pk=value)  # Will raise DoesNotExist if invalid
    return value


class Command(BaseCommand):
    help = "Index existing STIX objects from ArangoDB into ObjectValue table (post by post)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--feeds",
            type=validate_feed_id,
            nargs="+",
            help="Process only a specific feed by UUID",
        )
        parser.add_argument(
            "--posts",
            type=validate_post_id,
            nargs="+",
            help="Process only a specific post by UUID",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be processed without actually indexing",
        )

    def handle(self, *args, **options):
        feed_ids = options.get("feeds")
        dry_run = options.get("dry_run")

        # Get feeds to process
        feeds = FeedProfile.objects.all()
        if feed_ids:
            feeds = feeds.filter(pk__in=feed_ids)

        total_feeds = feeds.count()
        self.stdout.write(self.style.SUCCESS(f"Processing {total_feeds} feed(s)"))

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be made")
            )

        # Connect to ArangoDB
        client = ArangoClient(hosts=settings.ARANGODB_HOST_URL)
        db_name = settings.ARANGODB_DATABASE + "_database"
        db = client.db(
            db_name,
            username=settings.ARANGODB_USERNAME,
            password=settings.ARANGODB_PASSWORD,
            verify=True,
        )
        self.stdout.write(self.style.SUCCESS(f"Connected to ArangoDB: {db.db_name}"))

        total_posts = 0
        total_objects = 0
        failed_posts = []

        for feed in feeds:
            self.stdout.write(f"\nProcessing feed: {feed.id} ({feed.title})")
            self.stdout.write(f"Collection: {feed.vertex_collection}")

            try:
                # Check if collection exists
                if not db.has_collection(feed.vertex_collection):
                    self.stdout.write(
                        self.style.WARNING(
                            f"Collection {feed.vertex_collection} does not exist, skipping"
                        )
                    )
                    continue

                # Get all posts for this feed
                posts_query = File.objects.filter(feed=feed)

                posts = posts_query.select_related("post")
                feed_posts = posts.count()

                self.stdout.write(f"Found {feed_posts} post(s) to process")

                if feed_posts == 0:
                    continue

                feed_objects = 0

                for idx, post_file in enumerate(posts, 1):
                    post_report_id = f"report--{post_file.post_id}"
                    post_file.object_values.all().delete()  # Clear existing ObjectValues for this post

                    self.stdout.write(
                        f"  [{idx}/{feed_posts}] Processing post: {post_file.post_id}"
                    )

                    # Query objects for this specific post
                    post_query = f"""
                        FOR doc IN @@collection
                            FILTER doc._stixify_report_id == @report_id
                            RETURN doc
                    """

                    cursor = db.aql.execute(
                        post_query,
                        bind_vars={
                            "report_id": post_report_id,
                            "@collection": feed.vertex_collection,
                        },
                    )
                    post_objects = list(cursor)

                    if not post_objects:
                        self.stdout.write(
                            self.style.WARNING(
                                f"    No objects found for post {post_file.post_id}"
                            )
                        )
                        continue

                    self.stdout.write(f"    Found {len(post_objects)} objects")

                    if not dry_run:
                        try:
                            # Create a mock instance for the hook
                            mock_instance = type("MockInstance", (), {})()

                            # Extract IDs for the inserted_ids kwarg
                            inserted_ids = [
                                obj.get("id") for obj in post_objects if obj.get("id")
                            ]

                            # Call the hook
                            process_uploaded_objects_hook(
                                instance=mock_instance,
                                collection_name=feed.vertex_collection,
                                objects=post_objects,
                            )

                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"    Successfully indexed {len(post_objects)} objects"
                                )
                            )

                            feed_objects += len(post_objects)
                        except Exception as e:
                            self.stderr.write(
                                self.style.ERROR(
                                    f"    Error processing post {post_file.post_id}: {str(e)}"
                                )
                            )
                            logger.exception(
                                f"Error processing post {post_file.post_id} for feed {feed.id}"
                            )
                            failed_posts.append(
                                {
                                    "feed_id": str(feed.id),
                                    "feed_title": feed.title,
                                    "post_id": str(post_file.post_id),
                                    "error": str(e),
                                }
                            )
                    else:
                        feed_objects += len(post_objects)

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Feed {feed.id} complete: {feed_objects} objects from {feed_posts} posts"
                    )
                )

                total_posts += feed_posts
                total_objects += feed_objects

            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(f"Error processing feed {feed.id}: {str(e)}")
                )
                logger.exception(f"Error processing feed {feed.id}")
                continue

        # Summary
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS("SUMMARY"))
        self.stdout.write(f"Total feeds processed: {total_feeds}")
        self.stdout.write(f"Total posts processed: {total_posts}")
        self.stdout.write(f"Total objects indexed: {total_objects}")
        self.stdout.write(f"Failed posts: {len(failed_posts)}")

        if failed_posts:
            self.stdout.write("\n" + self.style.ERROR("FAILED POSTS:"))
            for failed in failed_posts:
                self.stdout.write(
                    f"  - Feed: {failed['feed_id']} ({failed['feed_title']}), "
                    f"Post: {failed['post_id']}, Error: {failed['error']}"
                )

        self.stdout.write("=" * 50)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "\nDRY RUN COMPLETE - No changes were made to the database"
                )
            )
