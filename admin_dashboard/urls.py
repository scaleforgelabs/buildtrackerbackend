from django.urls import path
from . import views

urlpatterns = [
    path('stats/', views.admin_stats_view, name='admin-stats'),
    path('users/', views.admin_users_view, name='admin-users'),
    path('users/<uuid:user_id>/role/', views.admin_update_user_role_view, name='admin-update-user-role'),
]
