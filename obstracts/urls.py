"""
URL configuration for obstracts project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from django.conf.urls.static import static
from .server import views
from rest_framework import routers
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from django.conf import settings
import dogesec_commons.objects.views as arango_views
from dogesec_commons.stixifier.views import ProfileView, ExtractorsView


from django.http import JsonResponse
def handler404(*args, **kwargs):
    return JsonResponse(dict(code=404, message='non-existent page'), status=404)

def handler500(*args, **kwargs):
    return JsonResponse(dict(code=500, message='internal server error'), status=500)



API_VERSION = "v1"

router = routers.SimpleRouter(use_regex_path=False)
router.register('profiles', ProfileView, 'profile-view')
router.register("feeds/<uuid:feed_id>/posts", views.FeedPostView, "feed-post-view")
router.register('feeds', views.FeedView, "feed-view")

router.register("posts", views.PostOnlyView, "post-view")


router.register('jobs', views.JobView, "job-view")

## objects
router.register('objects/smos', arango_views.SMOView, "object-view-smo")
router.register('objects/scos', arango_views.SCOView, "object-view-sco")
router.register('objects/sros', arango_views.SROView, "object-view-sro")
router.register('objects/sdos', arango_views.SDOView, "object-view-sdo")
router.register("object", arango_views.ObjectsWithReportsView, "object-view-orig")

# txt2stix views
router.register('extractors', ExtractorsView, "extractors-view")


urlpatterns = [
    path(f'api/{API_VERSION}/', include(router.urls)),
    path('admin/', admin.site.urls),
    # YOUR PATTERNS
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    # Optional UI:
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

