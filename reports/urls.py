from django.urls import path
from . import views

urlpatterns = [
    # Workspace reports
    path('workspaces/<uuid:workspaceId>/reports', views.workspace_reports, name='workspace_reports'),
    path('workspaces/<uuid:workspaceId>/reports/generate', views.generate_workspace_report, name='generate_workspace_report'),
    path('workspaces/<uuid:workspaceId>/reports/<uuid:id>', views.report_detail, name='report_detail'),
    path('workspaces/<uuid:workspaceId>/reports/<uuid:id>/export', views.export_report, name='export_report'),
    path('workspaces/<uuid:workspaceId>/reports/<uuid:id>/share', views.share_report, name='share_report'),
    path('workspaces/<uuid:workspaceId>/reports/schedule', views.schedule_report, name='schedule_report'),
    
    # User reports (workspace-scoped)
    path('workspaces/<uuid:workspaceId>/users/<uuid:userId>/reports', views.user_reports, name='user_reports'),
    path('workspaces/<uuid:workspaceId>/users/<uuid:userId>/reports/generate', views.generate_personal_report, name='generate_personal_report'),
    
    # Templates
    path('reports/templates', views.report_templates, name='report_templates'),
]