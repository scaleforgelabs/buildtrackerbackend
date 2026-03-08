from django.urls import path
from . import views

urlpatterns = [
    path('users/<uuid:userId>/module-access', views.user_module_access, name='user_module_access'),
    path('workspaces/<uuid:workspaceId>/module-analytics', views.workspace_module_analytics, name='workspace_module_analytics'),
    path('users/<uuid:userId>/module-preferences', views.user_module_preferences, name='user_module_preferences'),
    path('users/<uuid:userId>/module-insights', views.user_module_insights, name='user_module_insights'),
]
