from django.urls import path
from . import views

urlpatterns = [
    path('workspaces/<uuid:workspaceId>/dashboard/stats', views.workspace_dashboard_stats, name='workspace_dashboard_stats'),
    path('workspaces/<uuid:workspaceId>/dashboard/charts', views.workspace_dashboard_charts, name='workspace_dashboard_charts'),
    path('workspaces/<uuid:workspaceId>/analytics/performance', views.workspace_analytics_performance, name='workspace_analytics_performance'),
    path('workspaces/<uuid:workspaceId>/analytics/trends', views.workspace_analytics_trends, name='workspace_analytics_trends'),
    path('public/stats', views.public_stats, name='public_stats'),
]