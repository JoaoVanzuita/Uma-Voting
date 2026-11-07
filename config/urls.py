"""Roteamento raiz do projeto."""

from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from apps.accounts import urls as accounts_urls
from apps.voting import urls as voting_urls

handler403 = "apps.core.views.error_403"
handler404 = "apps.core.views.error_404"
handler500 = "apps.core.views.error_500"

participant_patterns = [
    *accounts_urls.participant_patterns,
    *voting_urls.participant_patterns,
]

admin_patterns = [
    *accounts_urls.admin_patterns,
    *voting_urls.admin_patterns,
]

urlpatterns = [
    path("", include("apps.core.urls")),
    path("", include((participant_patterns, "participant"), namespace="participant")),
    path("", include((admin_patterns, "admin"), namespace="admin")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
