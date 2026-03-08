from django.urls import path
from . import views

urlpatterns = [
    path('workspaces/<uuid:workspaceId>/system/health', views.system_health, name='system_health'),
    path('workspaces/<uuid:workspaceId>/system/metrics', views.system_metrics, name='system_metrics'),
    path('organizations/<uuid:id>/usage/detailed', views.organization_usage_detailed, name='organization_usage_detailed'),
]