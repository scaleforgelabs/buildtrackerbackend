from django.urls import path
from . import views

urlpatterns = [
    path('notifications', views.notifications_list, name='notifications-list'),
    path('notifications/<uuid:id>/read', views.mark_notification_read, name='notification-mark-read'),
    path('notifications/<uuid:id>', views.delete_notification, name='notification-delete'),
    path('notifications/mark-all-read', views.mark_all_read, name='notifications-mark-all-read'),
    path('notifications/unread-count', views.unread_count, name='notifications-unread-count'),
    path('workspaces/<uuid:workspaceId>/notifications', views.workspace_notifications, name='workspace-notifications'),
]
