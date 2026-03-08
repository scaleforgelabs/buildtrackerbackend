from django.contrib import admin
from .models import Report, ReportTemplate, ScheduledReport, SharedReport

@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['title', 'report_type', 'workspace', 'status', 'created_by', 'created_at']
    list_filter = ['report_type', 'status', 'format', 'created_at']
    search_fields = ['title', 'description', 'created_by__email']
    readonly_fields = ['id', 'job_id', 'created_at', 'updated_at']
    
@admin.register(ReportTemplate)
class ReportTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'report_type', 'category', 'is_active', 'created_at']
    list_filter = ['report_type', 'category', 'is_active']
    search_fields = ['name', 'description']
    
@admin.register(ScheduledReport)
class ScheduledReportAdmin(admin.ModelAdmin):
    list_display = ['report_type', 'workspace', 'frequency', 'next_run', 'is_active']
    list_filter = ['frequency', 'is_active', 'report_type']
    search_fields = ['workspace__name', 'created_by__email']
    
@admin.register(SharedReport)
class SharedReportAdmin(admin.ModelAdmin):
    list_display = ['report', 'shared_by', 'access_level', 'expires_at', 'created_at']
    list_filter = ['access_level', 'created_at']
    search_fields = ['report__title', 'shared_by__email']
    readonly_fields = ['share_token']