from django.urls import path
from . import views

urlpatterns = [
    path('workspaces/<str:workspaceId>/system/health', views.system_health, name='system_health'),
    path('workspaces/<str:workspaceId>/system/metrics', views.system_metrics, name='system_metrics'),
    path('workspaces/<str:workspaceId>/system/endpoint-analytics', views.workspace_endpoint_analytics, name='workspace_endpoint_analytics'),
    path('organizations/<uuid:id>/usage/detailed', views.organization_usage_detailed, name='organization_usage_detailed'),
]