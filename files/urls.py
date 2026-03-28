from django.urls import path
from . import views

urlpatterns = [
    path('workspaces/<uuid:workspaceId>/files/upload/', views.file_upload, name='file_upload'),
    path('files/<uuid:id>/', views.file_detail, name='file_detail'),
    path('files/<uuid:id>/delete/', views.file_delete, name='file_delete'),
    path('workspaces/<uuid:workspaceId>/files/', views.workspace_files, name='workspace_files'),
    path('workspaces/<uuid:workspaceId>/folders/create/', views.create_folder, name='create_folder'),
    path('workspaces/<uuid:workspaceId>/folders/<uuid:folderId>/upload/', views.upload_to_folder, name='upload_to_folder'),
    path('workspaces/<uuid:workspaceId>/folders/', views.folder_contents, name='root_folder_contents'),
    path('workspaces/<uuid:workspaceId>/folders/<uuid:folderId>/', views.folder_contents, name='folder_contents'),
    path('workspaces/<uuid:workspaceId>/folders/<uuid:folderId>/delete/', views.delete_folder, name='delete_folder'),
    path('workspaces/<uuid:workspaceId>/folders/<uuid:folderId>/download/', views.download_folder, name='download_folder'),
    path('files/<uuid:id>/download/', views.file_download, name='file_download'),
]