from datetime import timedelta
import os
from celery import Celery
# Set the default Django settings module for the 'celery' program.

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'obstracts.settings')

app = Celery('obstracts')


app.config_from_object('os:environ', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "auto_refresh_statistics_data": {
        "task": "obstracts.cjob.tasks.auto_refresh_statistics_data",
        "schedule": timedelta(minutes=10),
    }
}
