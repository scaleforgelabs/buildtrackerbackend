from django.contrib import admin
from .models import WorkspaceLog, AuditTrailLog, UserActivityLog, SystemEventLog

@admin.register(WorkspaceLog)
class WorkspaceLogAdmin(admin.ModelAdmin):
    list_display = ['workspace', 'user', 'log_type', 'severity', 'action', 'created_at']
    list_filter = ['log_type', 'severity', 'created_at', 'workspace']
    search_fields = ['action', 'description', 'user__email', 'workspace__name']
    readonly_fields = ['id', 'created_at']
    
@admin.register(AuditTrailLog)
class AuditTrailLogAdmin(admin.ModelAdmin):
    list_display = ['workspace', 'user', 'action', 'entity_type', 'created_at']
    list_filter = ['action', 'entity_type', 'created_at', 'workspace']
    search_fields = ['user__email', 'workspace__name', 'entity_type']
    readonly_fields = ['id', 'created_at']
    
@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'workspace', 'activity_type', 'module', 'created_at']
    list_filter = ['activity_type', 'module', 'created_at']
    search_fields = ['user__email', 'workspace__name', 'endpoint']
    readonly_fields = ['id', 'created_at']
    
@admin.register(SystemEventLog)
class SystemEventLogAdmin(admin.ModelAdmin):
    list_display = ['workspace', 'event_type', 'severity', 'message', 'resolved', 'created_at']
    list_filter = ['event_type', 'severity', 'resolved', 'created_at']
    search_fields = ['message', 'source', 'error_code']
    readonly_fields = ['id', 'created_at']