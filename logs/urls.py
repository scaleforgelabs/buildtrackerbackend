from django.urls import path
from . import views

urlpatterns = [
    path('workspaces/<uuid:workspaceId>/logs/detailed', views.workspace_logs_detailed, name='workspace_logs_detailed'),
    path('workspaces/<uuid:workspaceId>/logs/activity-timeline', views.workspace_activity_timeline, name='workspace_activity_timeline'),
    path('workspaces/<uuid:workspaceId>/logs/audit-trail', views.workspace_audit_trail, name='workspace_audit_trail'),
    path('workspaces/<uuid:workspaceId>/logs/user-activity/<uuid:userId>', views.workspace_user_activity, name='workspace_user_activity'),
    path('workspaces/<uuid:workspaceId>/logs/system-events', views.workspace_system_events, name='workspace_system_events'),
    path('workspaces/<uuid:workspaceId>/logs/export', views.workspace_logs_export, name='workspace_logs_export'),
    path('users/<uuid:userId>/activity-logs', views.user_activity_logs, name='user_activity_logs'),
]