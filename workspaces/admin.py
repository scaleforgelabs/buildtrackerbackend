from django.contrib import admin
from .models import Workspace, WorkspaceMember, WorkspaceInvitation

@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ['name', 'type', 'owner', 'created_at', 'no_of_tickets']
    list_filter = ['type', 'created_at']
    search_fields = ['name', 'description', 'owner__email']
    readonly_fields = ['id', 'created_at', 'updated_at']

@admin.register(WorkspaceMember)
class WorkspaceMemberAdmin(admin.ModelAdmin):
    list_display = ['user', 'workspace', 'role', 'user_status', 'joined_at']
    list_filter = ['role', 'user_status', 'joined_at']
    search_fields = ['user__email', 'workspace__name', 'name']
    readonly_fields = ['id', 'joined_at']

@admin.register(WorkspaceInvitation)
class WorkspaceInvitationAdmin(admin.ModelAdmin):
    list_display = ['email', 'workspace', 'role', 'status', 'created_at', 'expires_at']
    list_filter = ['role', 'status', 'created_at']
    search_fields = ['email', 'workspace__name']
    readonly_fields = ['id', 'token', 'created_at']