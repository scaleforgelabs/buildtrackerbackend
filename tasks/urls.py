from django.urls import path
from . import views

urlpatterns = [
    path('personal-tasks/', views.personal_tasks_list, name='personal_tasks_list'),
    path('personal-tasks/clear_all/', views.personal_tasks_list, name='personal_tasks_clear_all'), # handled via DELETE
    path('personal-tasks/<uuid:pk>/', views.personal_task_detail_view, name='personal_task_detail'),
    
    path('<uuid:workspaceId>/tasks/', views.workspace_tasks, name='workspace_tasks'),
    path('<uuid:workspaceId>/tasks/<uuid:id>/', views.task_detail, name='task_detail'),
    path('<uuid:workspaceId>/tasks/<uuid:id>/status/', views.update_task_status, name='update_task_status'),
    path('<uuid:workspaceId>/tasks/<uuid:id>/assign/', views.assign_task, name='assign_task'),
    path('<uuid:workspaceId>/tasks/<uuid:id>/blocker/', views.update_task_blocker, name='update_task_blocker'),
    path('<uuid:workspaceId>/tasks/by-milestone/<int:milestone>/', views.tasks_by_milestone, name='tasks_by_milestone'),
    path('<uuid:workspaceId>/tasks/by-sprint/<int:sprint>/', views.tasks_by_sprint, name='tasks_by_sprint'),
    path('<uuid:workspaceId>/tasks/<uuid:taskId>/comments/', views.task_comments, name='task_comments'),
    path('<uuid:workspaceId>/tasks/<uuid:taskId>/comments/<uuid:commentId>/', views.task_comment_detail, name='task_comment_detail'),
    path('<uuid:workspaceId>/tasks/attachments/<uuid:attachmentId>/download/', views.download_task_attachment, name='task_attachment_download'),
    path('<uuid:workspaceId>/tasks/comments/attachments/<uuid:attachmentId>/download/', views.download_task_comment_attachment, name='task_comment_attachment_download'),
]