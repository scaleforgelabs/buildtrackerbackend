from django.urls import path
from . import views

urlpatterns = [
    path('', views.workspaces_list_create, name='workspaces_list_create'),
    path('<str:id>/', views.workspace_detail, name='workspace_detail'),
    path('<str:id>/members/', views.workspace_members, name='workspace_members'),
    path('<str:id>/members/<uuid:userId>/', views.workspace_member_detail, name='workspace_member_detail'),
    path('<str:id>/invitations/', views.workspace_invitations, name='workspace_invitations'),
    path('<str:id>/invitations/<uuid:invitationId>/', views.workspace_invitation_detail, name='workspace_invitation_detail'),
    path('invitations/<str:token>/details/', views.get_invitation_details, name='get_invitation_details'),
    path('invitations/accept/', views.accept_workspace_invitation, name='accept_workspace_invitation'),
    path('<str:workspaceId>/settings', views.workspace_settings, name='workspace_settings'),
]