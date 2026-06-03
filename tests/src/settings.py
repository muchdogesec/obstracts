from obstracts.settings import *

ARANGODB_DATABASE = "obstracts_test"
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-cache-name",
    }
}
