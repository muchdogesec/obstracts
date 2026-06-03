
from django.apps import AppConfig
from django.utils import timezone


class ServerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'obstracts.server'
    label = 'obstracts'

    def ready(self):
        from obstracts.server.statistics import ensure_statistics_data
        ensure_statistics_data(timezone.now())
        return super().ready()