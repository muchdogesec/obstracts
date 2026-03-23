import os

from django.core.management.base import BaseCommand
from django.conf import settings

from obstracts.classifier import tasks
from obstracts.server import models
import uuid

import logging
logging.basicConfig()
logging.getLogger(__name__).setLevel(logging.INFO)

class Command(BaseCommand):
    help = "Run HDBSCAN clustering once within a tracked Job context."

    def add_arguments(self, parser):
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

        if force:
            model_path = settings.CLASSIFIER_MODEL_PATH
            if os.path.exists(model_path):
                os.remove(model_path)
                self.stdout.write(f"Removed existing model: {model_path}")

        self.stdout.write("Running clustering once...")
        tasks.run_clustering(
            force=force,
            workers=workers,
        )
        self.stdout.write(self.style.SUCCESS("Done."))
