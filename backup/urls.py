from django.urls import path
from . import views

urlpatterns = [
    path('workspaces/<uuid:workspaceId>/backup/create', views.create_backup, name='create_backup'),
    path('workspaces/<uuid:workspaceId>/backups', views.list_backups, name='list_backups'),
    path('workspaces/<uuid:workspaceId>/data/export', views.create_export, name='create_export'),
    path('workspaces/<uuid:workspaceId>/exports', views.list_exports, name='list_exports'),
    path('download/backup/<uuid:backup_id>/', views.download_backup, name='download_backup'),
    path('download/export/<uuid:export_id>/', views.download_export, name='download_export'),
]