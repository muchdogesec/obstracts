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
from django.urls import path
from django.urls import include, path
from .server import views
from rest_framework import routers
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

API_VERSION = "v1"

router = routers.SimpleRouter()
router.register('profiles', views.ProfileView, "profile-view")
router.register('feeds', views.FeedView, "feed-view")
router.register('jobs', views.JobView, "job-view")
router.register('objects', views.ObjectsView, "objects-view")
txt2stix_router = routers.SimpleRouter()
txt2stix_router.register('extractors', views.ExtractorsView, "extractors-view")
txt2stix_router.register('whitelists', views.WhitelistsView, "whitelists-view")
txt2stix_router.register('aliases', views.AliasesView, "aliases-view")

urlpatterns = [
    path(f'api/{API_VERSION}/', include(router.urls)),
    path(f'api/{API_VERSION}/txt2stix/', include(txt2stix_router.urls)),
    path('admin/', admin.site.urls),

    # YOUR PATTERNS
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    # Optional UI:
    path('schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
