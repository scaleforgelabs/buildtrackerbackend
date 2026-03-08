from django.urls import path
from . import views

urlpatterns = [
    path('<uuid:workspaceId>/integrations/', views.integrations, name='integrations'),
    path('<uuid:workspaceId>/integrations/<uuid:id>/', views.integration_detail, name='integration_detail'),
]