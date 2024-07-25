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
from file2txt.openai_processor import OpenAIMDCleaner
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
        if self.profile.prettify_with_ai:
            openai_cleaner = OpenAIMDCleaner()
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
        
        self.bundle = bundler.to_json()
        self.bundle_file = self.tmpdir/f"bundle_{self.post_id}.json"
        self.bundle_file.write_text(self.bundle)

        if ai_extractor_session.initialized:
            (self.tmpdir/f"conversation_{self.post_id}.md").write_text(ai_extractor_session.get_conversation())


    def process(self):
        logging.info(f"running file2txt on {self.task_name}")
        self.file2txt()
        logging.info(f"running txt2stix on {self.task_name}")
        self.txt2stix()
        logging.info(f"uploading {self.task_name} to arangodb via stix2arango")
        self.upload_to_arango()



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




def test_gg():
    logging.basicConfig(level=logging.INFO)
    post = {
      "id": "7b53d989-5263-46fd-9ad3-370dee4f9e55",
      "datetime_added": "2024-07-11T14:07:19.356496Z",
      "datetime_updated": "2024-07-11T14:07:19.356508Z",
      "title": "Macau government websites hit with cyberattack by suspected foreign hackers",
      "description": "<html><body><div><span class=\"wysiwyg-parsed-content\"><p class=\"paragraph\"> At least five Macau government websites were knocked offline by suspected foreign hackers for almost an hour earlier this week, several Chinese media outlets <a href=\"https://www.orangenews.hk/china/1230412/%E6%BE%B3%E9%96%80%E5%A4%9A%E5%80%8B%E9%83%A8%E9%96%80%E7%B6%B2%E7%AB%99%E9%81%AD%E6%94%BB%E6%93%8A%E6%9C%8D%E5%8B%99%E4%B8%80%E5%BA%A6%E5%8F%97%E9%98%BB-%E7%95%B6%E5%B1%80%E8%B2%AC%E6%88%90%E9%9B%BB%E8%A8%8A%E5%95%86%E5%BE%B9%E6%9F%A5.shtml\" target=\"_blank\" rel=\"noopener noreferrer\">reported</a>, citing local security officials. </p><p class=\"paragraph\"> A distributed denial-of-service attack (DDoS) affected, among others, the websites of Macau’s security service, police force, fire and rescue services, and the academy for public security forces. </p><p class=\"paragraph\"> The densely populated Macau is a “special administrative region” on the south coast of China. Local police have launched a criminal investigation into the incidents to trace the source of the criminal activity. </p><p class=\"paragraph\"> The attack occurred on Wednesday evening and likely originated “from overseas,” according to local officials. </p><p class=\"paragraph\"> Following the incident, Macau’s authorities carried out an emergency response “in collaboration with telecommunication operators to promptly restore regular services,” <a href=\"https://macaudailytimes.com.mo/websites-of-office-of-the-secretary-for-security-targeted-in-a-cyber-attack.html\" target=\"_blank\" rel=\"noopener noreferrer\">said</a> the region’s Secretary for Security, Wong Sio Chak. </p><p class=\"paragraph\"> The country’s security forces also instructed Macau Telecom, which provides the services to block DDoS attacks, to investigate the incident and submit a report and improvement plan to prevent similar attacks in the future. </p><p class=\"paragraph\"> It is not clear what hacker group was behind the incident or what their motives were. </p><p class=\"paragraph\"> Local media claimed that the latest attacks followed a surge in cyber activities in the region. According to a recent <a href=\"https://macaonews.org/news/city/macau-cyberattacks-cyber-security-attacks-macao/\" target=\"_blank\" rel=\"noopener noreferrer\">report</a>, the number of cyberattacks targeting Macau’s critical infrastructure last year has more than tripled since 2020. </p></span><div class=\"article__adunit\"><div class=\"mb-4\"><p>Get more insights with the </p><p>Recorded Future</p><p>Intelligence Cloud.</p></div><a class=\"underline\" target=\"_blank\" rel=\"noopener noreferrer\" href=\"https://www.recordedfuture.com/platform?mtm_campaign=ad-unit-record\">Learn more.</a></div></div></body></html>",
      "link": "https://therecord.media/macau-government-websites-hit-with-cyberattack",
      "pubdate": "2024-07-11T13:45:41Z",
      "author": "",
      "is_full_text": True,
      "content_type": "text/html; charset=utf-8",
      "categories": [
        "cybercrime",
        "news-briefs",
        "government"
      ]
    }
    job = models.Job.objects.first()

    p = ObstractsProcessor(post, job)
    p.process()


    #import obstracts.cjob.obstracts_helpers
    return p