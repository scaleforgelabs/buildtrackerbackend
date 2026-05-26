from django.urls import path
from . import views

urlpatterns = [
    path('workspaces/<uuid:workspaceId>/projects/', views.gantt_projects, name='gantt_projects'),
    path('workspaces/<uuid:workspaceId>/projects/<uuid:projectId>/', views.gantt_project_detail, name='gantt_project_detail'),
    path('workspaces/<uuid:workspaceId>/projects/<uuid:projectId>/tasks/', views.gantt_tasks, name='gantt_tasks'),
    path('workspaces/<uuid:workspaceId>/projects/<uuid:projectId>/tasks/<uuid:taskId>/', views.gantt_task_detail, name='gantt_task_detail'),
    path('workspaces/<uuid:workspaceId>/projects/<uuid:projectId>/tasks/bulk-update/', views.gantt_bulk_update, name='gantt_bulk_update'),
    path('workspaces/<uuid:workspaceId>/projects/<uuid:projectId>/import/', views.gantt_import, name='gantt_import'),
    path('workspaces/<uuid:workspaceId>/projects/<uuid:projectId>/export/', views.gantt_export, name='gantt_export'),
]
