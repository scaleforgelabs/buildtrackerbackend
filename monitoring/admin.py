from django.contrib import admin
from .models import SystemMetric, SystemAlert, UsageMetric

@admin.register(SystemMetric)
class SystemMetricAdmin(admin.ModelAdmin):
    list_display = ['metric_name', 'metric_type', 'value', 'unit', 'timestamp']
    list_filter = ['metric_type', 'metric_name', 'timestamp']
    search_fields = ['metric_name']
    readonly_fields = ['id', 'timestamp']
    
@admin.register(SystemAlert)
class SystemAlertAdmin(admin.ModelAdmin):
    list_display = ['title', 'alert_type', 'severity', 'status', 'created_at']
    list_filter = ['severity', 'status', 'alert_type', 'created_at']
    search_fields = ['title', 'description']
    readonly_fields = ['id', 'created_at']
    
@admin.register(UsageMetric)
class UsageMetricAdmin(admin.ModelAdmin):
    list_display = ['organization', 'metric_name', 'value', 'unit', 'cost', 'date']
    list_filter = ['metric_name', 'date', 'organization']
    search_fields = ['organization__name', 'metric_name']
    readonly_fields = ['id']