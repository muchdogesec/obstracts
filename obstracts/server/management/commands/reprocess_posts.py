import itertools
import json
from django.core.management.base import BaseCommand, CommandError
import importlib.util
import io
import logging
from pathlib import Path

from obstracts.server import models as ob_models
from history4feed.app import models as h4f_models
from dogesec_commons.stixifier.stixifier import (
    StixifyProcessor,
    ReportProperties,
    all_extractors,
)
from txt2stix.txt2stix import txt2stixBundler, Txt2StixData
from django.core.files.base import File as DjangoFile
from django.conf import settings
import typing

from obstracts.server.views import PostOnlyView

if typing.TYPE_CHECKING:
    from obstracts import settings

import txt2stix.txt2stix
from stix2arango.stix2arango import Stix2Arango


def upload_to_arango(dsc_processor: StixifyProcessor, bundle):
    s2a = Stix2Arango(
        file="",
        database=settings.ARANGODB_DATABASE,
        collection=dsc_processor.collection_name,
        stix2arango_note=f"stixifier-report--{dsc_processor.report_id}",
        ignore_embedded_relationships=dsc_processor.profile.ignore_embedded_relationships,
        ignore_embedded_relationships_smo=dsc_processor.profile.ignore_embedded_relationships_smo,
        ignore_embedded_relationships_sro=dsc_processor.profile.ignore_embedded_relationships_sro,
        include_embedded_relationships_attributes=dsc_processor.profile.include_embedded_relationships_attributes,
        host_url=settings.ARANGODB_HOST_URL,
        username=settings.ARANGODB_USERNAME,
        password=settings.ARANGODB_PASSWORD,
    )
    s2a.arangodb_extra_data.update(dsc_processor.extra_data)
    s2a.run(data=bundle)


def run_txt2stix(
    dsc_processor: StixifyProcessor, input_text: str, txt2stix_data: Txt2StixData
):
    extractors = all_extractors(dsc_processor.profile.extractions)
    extractors_map = {}
    for extractor in extractors.values():
        if extractors_map.get(extractor.type):
            extractors_map[extractor.type][extractor.slug] = extractor
        else:
            extractors_map[extractor.type] = {extractor.slug: extractor}

    dsc_processor.bundler = txt2stixBundler(
        dsc_processor.report_prop.name,
        identity=dsc_processor.report_prop.identity,
        tlp_level=dsc_processor.report_prop.tlp_level,
        confidence=dsc_processor.report_prop.confidence,
        labels=dsc_processor.report_prop.labels,
        description=input_text,
        extractors=extractors,
        report_id=dsc_processor.report_id,
        created=dsc_processor.report_prop.created,
        **dsc_processor.report_prop.kwargs,
    )
    dsc_processor.extra_data["_stixify_report_id"] = str(
        dsc_processor.bundler.report.id
    )
    txt2stix.txt2stix.processing_phase(
        dsc_processor.bundler,
        input_text,
        txt2stix_data,
        ai_create_attack_flow=dsc_processor.profile.ai_create_attack_flow,
        ai_create_attack_navigator_layer=dsc_processor.profile.ai_create_attack_navigator_layer,
        ai_settings_relationships=dsc_processor.profile.ai_settings_relationships,
        ai_content_check_provider=dsc_processor.profile.ai_content_check_provider,
    )
    return dsc_processor.bundler


def filter_file(file: ob_models.File):
    return True


class Command(BaseCommand):
    help = "Reprocess posts matching a user-provided filter file. Does not create Job entries."

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

    def handle(self, *args, **options):
        limit = options.get("limit")
        dry_run = options.get("dry_run")

        matches: list[ob_models.File] = []
        kwargs = {}
        if options.get("feed_id"):
            kwargs["feed_id__in"] = options["feed_id"]
        if options.get("post_id"):
            kwargs["post__id__in"] = options["post_id"]
        qs = ob_models.File.objects.filter(
            txt2stix_data__isnull=False,
            **kwargs
        )  # .order_by("id")
        for post_file in qs:
            try:
                if filter_file(post_file):
                    matches.append(post_file)
            except Exception:
                logging.exception(
                    "error while evaluating filter for post %s", post_file.post_id
                )

        if limit:
            matches = matches[:limit]

        if dry_run:
            self.stdout.write(f"Dry run: {len(matches)} posts match the filter")
            for p in matches:
                self.stdout.write(f"- post {p.post_id} title={p.post.title}")
            return

        self.stdout.write(f"Processing {len(matches)} posts")
        processed = 0
        failed = 0
        for file_obj in matches:
            post = file_obj.post
            try:
                feedp = ob_models.FeedProfile.objects.get(feed_id=post.feed.id)
                profile = file_obj.profile

                file_obj, _ = ob_models.File.objects.update_or_create(
                    post_id=post.id,
                    defaults={
                        "feed": feedp,
                        "profile": profile,
                    },
                )
                data = Txt2StixData.model_validate(file_obj.txt2stix_data)
                for d in itertools.chain([], *data.extractions.values()):
                    d.pop("error", None)

                # Build input stream for processor
                report_descr = file_obj.markdown_file.open().read()
                # report_descr = b"sample"
                stream = io.BytesIO(report_descr)
                stream.name = f"post-{post.id}.md"
                PostOnlyView.remove_report_objects(file_obj)

                report_descr = report_descr.decode()

                processor = StixifyProcessor(
                    stream,
                    profile,
                    job_id=f"{post.id}+reprocess",
                    file2txt_mode="md",
                    report_id=post.id,
                    base_url=post.link,
                )
                processor.collection_name = feedp.collection_name

                properties = ReportProperties(
                    name=post.title,
                    identity=file_obj.feed.identity,
                    tlp_level="clear",
                    confidence=0,
                    labels=[f"tag.{cat.name}" for cat in post.categories.all()],
                    created=post.pubdate,
                    kwargs=dict(
                        external_references=[
                            dict(source_name="post_link", url=post.link),
                            dict(
                                source_name="obstracts_feed_id",
                                external_id=str(feedp.id),
                            ),
                            dict(
                                source_name="obstracts_profile_id",
                                external_id=str(profile.id) if profile else None,
                            ),
                        ]
                    ),
                )
                processor.setup(
                    properties,
                    dict(
                        _obstracts_feed_id=str(feedp.id),
                        _obstracts_post_id=str(post.id),
                    ),
                )

                # Run the processor (this creates md file and images in processor)
                bundler = run_txt2stix(processor, report_descr, data)
                bundle = json.loads(bundler.to_json())
                upload_to_arango(processor, bundle)

                # copy processor results
                file_obj.processed = True

                file_obj.txt2stix_data = data.model_dump(
                    mode="json",
                    exclude_defaults=True,
                    exclude_unset=True,
                    exclude_none=True,
                )
                file_obj.save(
                    update_fields=[
                        "processed",
                        "txt2stix_data",
                    ]
                )

                processed += 1
                self.stdout.write(f"Processed post {post.id}")
            except Exception:
                logging.exception("processing failed for post %s", post.id)
                failed += 1
                raise

        self.stdout.write(f"Done. processed={processed} failed={failed}")
