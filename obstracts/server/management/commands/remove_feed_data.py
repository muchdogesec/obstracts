from collections import defaultdict
import sys
from django.db.models.signals import *
from django.db import connection, transaction
import os

from django.core.management.base import BaseCommand
from django.conf import settings

from obstracts.classifier import tasks
from obstracts.server import models
import uuid

import logging
logging.basicConfig()
logging.getLogger(__name__).setLevel(logging.INFO)


class DryRun(Exception):
    def __init__(self, *args, would_delete=None):
        super().__init__(*args)
        self.would_delete = would_delete

    def __str__(self):
        return f"DRY RUN --- NOT DELETING: {self.would_delete}"


class DisableSignals(object):
    def __init__(self, disabled_signals=None):
        self.stashed_signals = defaultdict(list)
        self.disabled_signals = disabled_signals or [
            pre_init, post_init,
            pre_save, post_save,
            pre_delete, post_delete,
            pre_migrate, post_migrate,
        ]

    def __enter__(self):
        for signal in self.disabled_signals:
            self.disconnect(signal)

    def __exit__(self, exc_type, exc_val, exc_tb):
        for signal in list(self.stashed_signals):
            self.reconnect(signal)

    def disconnect(self, signal):
        self.stashed_signals[signal] = signal.receivers
        signal.receivers = []

    def reconnect(self, signal):
        signal.receivers = self.stashed_signals.get(signal, [])
        del self.stashed_signals[signal]

class Command(BaseCommand):
    help = "Run HDBSCAN clustering once within a tracked Job context."

    def add_arguments(self, parser):
        parser.add_argument(
            "feed_id",
            help="id of feed to delete"
        )

        parser.add_argument(
            "--dry-run",
            "-N",
            action='store_true',
            help="dont actually delete, just show objects that would be removed"
        )

    def handle(self, *args, feed_id, **options):
        dry_run = options['dry_run']

        try:
            with (transaction.atomic(), DisableSignals()):
                feed = models.h4f_models.Feed.objects.get(id=feed_id)
                deleted = feed.delete()
                if dry_run:
                    raise DryRun(would_delete=deleted)
                feed.id = feed_id
                feed.save()
                self.stdout.write(self.style.SUCCESS(f"DELETED SUCCESSFULLY: {deleted}"))
        except DryRun as e:
            self.stdout.write(self.style.WARNING(e))
            sys.exit(0)
