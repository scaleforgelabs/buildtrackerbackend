from django.contrib import admin
from .models import BackupJob, ExportJob

@admin.register(BackupJob)
class BackupJobAdmin(admin.ModelAdmin):
    list_display = ['workspace', 'backup_type', 'status', 'include_files', 'encryption_enabled', 'created_at']
    list_filter = ['backup_type', 'status', 'include_files', 'encryption_enabled', 'created_at']
    search_fields = ['workspace__name', 'created_by__email']
    readonly_fields = ['id', 'created_at', 'completed_at']

@admin.register(ExportJob)
class ExportJobAdmin(admin.ModelAdmin):
    list_display = ['workspace', 'export_type', 'format', 'status', 'created_at']
    list_filter = ['export_type', 'format', 'status', 'created_at']
    search_fields = ['workspace__name', 'created_by__email']
    readonly_fields = ['id', 'created_at', 'completed_at']