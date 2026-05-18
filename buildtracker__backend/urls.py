from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework import permissions
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from monitoring.views import backend_endpoint_analytics

urlpatterns = [
    path('admin/', admin.site.urls),
    path('endpoint-analytics/', backend_endpoint_analytics, name='backend_endpoint_analytics'),
    path('api/', include('core.urls')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('swagger/', SpectacularSwaggerView.as_view(url_name='schema', permission_classes=[permissions.AllowAny]), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema', permission_classes=[permissions.AllowAny]), name='redoc'),
    path('api/auth/', include('auth_func.urls')),
    path('api/workspaces/', include('workspaces.urls')),
    path('api/tasks/', include('tasks.urls')),
    path('api/wiki/', include('wiki.urls')),
    path('api/integrations/', include('integrations.urls')),
    path('api/files/', include('files.urls')),
    path('api/waitlist/', include('waitlist.urls')),
    path('api/quicklinks/', include('quicklinks.urls')),
    path('api/search/', include('search.urls')),
    path('api/reports/', include('reports.urls')),
    path('api/monitoring/', include('monitoring.urls')),
    path('api/subscriptions/', include('subscriptions.urls')),
    path('api/analytics/', include('analytics.urls')),
    path('api/backup/', include('backup.urls')),
    path('api/logs/', include('logs.urls')),
    path('api/modules/', include('modules.urls')),
    path('api/organizations/', include('organizations.urls')),
    path('api/checkins/', include('checkins.urls')),
    path('api/', include('notifications.urls')),
    path('api/', include('widgets.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
