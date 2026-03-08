from django.urls import path
from . import views

urlpatterns = [
    path('global', views.global_search, name='global_search'),
    path('workspaces/<uuid:workspaceId>/search', views.workspace_search, name='workspace_search'),
]