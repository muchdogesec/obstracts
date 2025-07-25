
from obstracts.server.models import FeedProfile
from history4feed.app import models as h4f_models



def make_h4f_job(feed: FeedProfile):
    job = h4f_models.Job.objects.create(feed_id=feed.id)
    return job