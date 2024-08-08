import json
import logging
import os
from pathlib import Path
import shutil

from obstracts.cjob import arango_view_helper
from ..server import models
from ..server.serializers import ProfileSerializer
import tempfile
from file2txt.converter import convert_file
from txt2stix import txt2stix
from txt2stix.stix import txt2stixBundler
from txt2stix.ai_session import GenericAIExtractor
from stix2arango.stix2arango import Stix2Arango
from django.conf import settings


def all_extractors(names, _all=False):
    retval = {}
    extractors = txt2stix.extractions.parse_extraction_config(txt2stix.INCLUDES_PATH).values()
    for extractor in extractors:
        if _all or extractor.slug in names:
            retval[extractor.slug] = extractor
    return retval

def process_post_file2txt(post, job: models.Job):
    profile = job.profile


class ObstractsProcessor:
    VIEW_NAME = "obstracts"
    TLP_LEVEL = 'clear'

    view_object = None
    def __init__(self, post, job: models.Job) -> None:
        self.job = job
        self.post_id = post['id']
        self.profile = self.job.profile
        self.collection_name = self.job.feed.collection_name
        self.h4fpost = post
        self.tmpdir = Path(tempfile.mkdtemp(prefix='obstracts_'))
        self.filename = self.tmpdir/f"post_{self.post_id}.html"
        self.filename.write_text(post["description"])

        self.task_name = f"{self.job.feed_id}/{self.job.id}/{self.post_id}"
        
        self.visions_keyfile = os.path.abspath(os.path.join(os.curdir, 'google_vision_key/key.json'))

    def file2txt(self):
        openai_cleaner = None
        output = convert_file("html", self.filename, image_processor_key=self.visions_keyfile, process_raw_image_urls=self.job.profile.extract_text_from_image, md_cleaner=openai_cleaner)
        self.output_md = "\n".join(output)
        self.md_file = self.tmpdir/f"post_md_{self.post_id}.md"
        self.md_file.write_text(self.output_md)

    def txt2stix(self):
        extractors = all_extractors(self.profile.extractions)
        extractors_map = {}
        for extractor in extractors.values():
            if extractors_map.get(extractor.type):
                extractors_map[extractor.type][extractor.slug] = extractor
            else:
                extractors_map[extractor.type] = {extractor.slug: extractor}
        aliases = all_extractors(self.profile.aliases)
        whitelists = all_extractors(self.profile.whitelists)

        bundler = txt2stixBundler(f"obstracts_post_{self.post_id}", identity=None, tlp_level=self.TLP_LEVEL, confidence=None, labels=None, description=self.output_md, extractors=extractors, job_id=self.post_id)
        input_text = txt2stix.remove_data_images(self.output_md)
        aliased_input = txt2stix.aliases.transform_all(aliases.values(), input_text)
        bundler.add_note(json.dumps(ProfileSerializer(self.profile).data), "Obstracts Profile")
        bundler.whitelisted_values = txt2stix.lookups.merge_whitelists(whitelists.values())

        ai_extractor_session = GenericAIExtractor.openai()
        all_extracts = txt2stix.extract_all(bundler, extractors_map, aliased_input, ai_extractor=ai_extractor_session)
 
        if self.profile.relationship_mode == models.RelationshipMode.AI and sum(map(lambda x: len(x), all_extracts.values())):
            txt2stix.extract_relationships_with_ai(bundler, aliased_input, all_extracts, ai_extractor_session)
        
        self.write_bundle(bundler)

        if ai_extractor_session.initialized:
            (self.tmpdir/f"conversation_{self.post_id}.md").write_text(ai_extractor_session.get_conversation())


    def process(self):
        logging.info(f"running file2txt on {self.task_name}")
        self.file2txt()
        logging.info(f"running txt2stix on {self.task_name}")
        self.txt2stix()
        logging.info(f"uploading {self.task_name} to arangodb via stix2arango")
        self.upload_to_arango()

    def write_bundle(self, bundler: txt2stixBundler):
        bundle = json.loads(bundler.to_json())
        for obj in bundle['objects']:
            obj['_obstracts_feed_id'] = str(self.job.feed_id)
            obj['_obstracts_post_id'] = str(self.post_id)
        self.bundle = json.dumps(bundle, indent=4)
        self.bundle_file = self.tmpdir/f"bundle_{self.post_id}.json"
        self.bundle_file.write_text(self.bundle)
        

    def upload_to_arango(self):
        s2a = Stix2Arango(
            file=str(self.bundle_file),
            database=settings.ARANGODB_DATABASE,
            collection=self.collection_name,
            stix2arango_note=f"obstracts-post--{self.post_id}",
            ignore_embedded_relationships=False,
            host_url=settings.ARANGODB_HOST_URL,
            username=settings.ARANGODB_USERNAME,
            password=settings.ARANGODB_PASSWORD,
        )
        arango_view_helper.link_one_collection(s2a.arango.db, settings.VIEW_NAME, f"{self.collection_name}_edge_collection")
        arango_view_helper.link_one_collection(s2a.arango.db, settings.VIEW_NAME, f"{self.collection_name}_vertex_collection")
        s2a.run()
    
    @classmethod
    def get_view(cls, s2a: Stix2Arango):
        if cls.view_object:
            return cls.view_object
        try:
            cls.view_object = s2a.arango.db.create_view(cls.VIEW_NAME, "arangosearch", {})
        except BaseException as e:
            logging.exception(e)
            cls.view_object = s2a.arango.db.view(cls.VIEW_NAME)
        return cls.view_object

    

    def __del__(self):
        shutil.rmtree(self.tmpdir)