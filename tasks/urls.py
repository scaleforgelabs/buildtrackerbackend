from django.urls import path
from . import views
from . import sprint_views

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
    path('workspaces/<uuid:workspaceId>/<uuid:id>/attachments/', views.task_attachment_upload, name='task_attachment_upload'),
    path('workspaces/<uuid:workspaceId>/attachments/<uuid:attachmentId>/download/', views.download_task_attachment, name='task_attachment_download'),
    path('workspaces/<uuid:workspaceId>/comments/attachments/<uuid:attachmentId>/download/', views.download_task_comment_attachment, name='task_comment_attachment_download'),

    # Sprint endpoints
    path('workspaces/<uuid:workspaceId>/sprints/', sprint_views.sprint_list, name='sprint_list'),
    path('workspaces/<uuid:workspaceId>/sprints/velocity/', sprint_views.sprint_velocity, name='sprint_velocity'),
    path('workspaces/<uuid:workspaceId>/sprints/backlog/', sprint_views.backlog_tasks, name='backlog_tasks'),
    path('workspaces/<uuid:workspaceId>/sprints/<uuid:sprintId>/', sprint_views.sprint_detail, name='sprint_detail'),
    path('workspaces/<uuid:workspaceId>/sprints/<uuid:sprintId>/publish/', sprint_views.sprint_publish, name='sprint_publish'),
    path('workspaces/<uuid:workspaceId>/sprints/<uuid:sprintId>/complete/', sprint_views.sprint_complete, name='sprint_complete'),
    path('workspaces/<uuid:workspaceId>/sprints/<uuid:sprintId>/tasks/', sprint_views.sprint_tasks, name='sprint_tasks'),
    path('workspaces/<uuid:workspaceId>/sprints/<uuid:sprintId>/tasks/assign/', sprint_views.assign_tasks_to_sprint, name='assign_tasks_to_sprint'),
    path('workspaces/<uuid:workspaceId>/tasks/<uuid:taskId>/remove-sprint/', sprint_views.remove_task_from_sprint, name='remove_task_from_sprint'),
]