from django.urls import path
from . import views

urlpatterns = [
    path('stats/', views.admin_stats_view, name='admin-stats'),
    path('users/', views.admin_users_view, name='admin-users'),
    path('users/<uuid:user_id>/role/', views.admin_update_user_role_view, name='admin-update-user-role'),
    path('users/<uuid:user_id>/delete/', views.admin_delete_user_view, name='admin-delete-user'),
    path('users/<uuid:user_id>/suspend/', views.admin_suspend_user_view, name='admin-suspend-user'),
    path('workspaces/', views.admin_workspaces_view, name='admin-workspaces'),
    path('analytics/', views.admin_analytics_view, name='admin-analytics'),
    path('subscriptions/', views.admin_subscriptions_view, name='admin-subscriptions'),
    path('newsletter/', views.admin_newsletter_view, name='admin-newsletter'),
]
