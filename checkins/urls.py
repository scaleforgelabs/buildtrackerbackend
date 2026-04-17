from django.urls import path
from . import views

urlpatterns = [
    # GET today's team feed / POST submit check-in
    path('workspaces/<uuid:workspaceId>/', views.workspace_checkins, name='workspace-checkins'),

    # GET current user's check-in history
    path('workspaces/<uuid:workspaceId>/mine/', views.my_checkins, name='my-checkins'),

    # GET whether current user has checked in today
    path('workspaces/<uuid:workspaceId>/status/', views.checkin_status, name='checkin-status'),
]
