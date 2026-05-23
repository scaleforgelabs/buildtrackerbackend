from django.urls import path
from . import views

urlpatterns = [
    path('personal-tasks/', views.personal_tasks_list, name='personal_tasks_list'),
    path('personal-tasks/clear_all/', views.personal_tasks_list, name='personal_tasks_clear_all'), # handled via DELETE
    path('personal-tasks/<uuid:pk>/', views.personal_task_detail_view, name='personal_task_detail'),
    
    path('workspaces/<uuid:workspaceId>/', views.workspace_tasks, name='workspace_tasks'),
    path('workspaces/<str:workspaceId>/ticket/<int:ticketNumber>/', views.task_by_ticket, name='task_by_ticket'),
    path('workspaces/<uuid:workspaceId>/<uuid:id>/', views.task_detail, name='task_detail'),
    path('workspaces/<uuid:workspaceId>/<uuid:id>/status/', views.update_task_status, name='update_task_status'),
    path('workspaces/<uuid:workspaceId>/<uuid:id>/assign/', views.assign_task, name='assign_task'),
    path('workspaces/<uuid:workspaceId>/<uuid:id>/blocker/', views.update_task_blocker, name='update_task_blocker'),
    path('workspaces/<uuid:workspaceId>/by-milestone/<int:milestone>/', views.tasks_by_milestone, name='tasks_by_milestone'),
    path('workspaces/<uuid:workspaceId>/by-sprint/<int:sprint>/', views.tasks_by_sprint, name='tasks_by_sprint'),
    path('workspaces/<uuid:workspaceId>/<uuid:taskId>/comments/', views.task_comments, name='task_comments'),
    path('workspaces/<uuid:workspaceId>/<uuid:taskId>/comments/<uuid:commentId>/', views.task_comment_detail, name='task_comment_detail'),
    path('workspaces/<uuid:workspaceId>/attachments/<uuid:attachmentId>/download/', views.download_task_attachment, name='task_attachment_download'),
    path('workspaces/<uuid:workspaceId>/comments/attachments/<uuid:attachmentId>/download/', views.download_task_comment_attachment, name='task_comment_attachment_download'),
]