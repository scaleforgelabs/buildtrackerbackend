from django.contrib import admin
from .models import DashboardWidget, WidgetLayout


@admin.register(DashboardWidget)
class DashboardWidgetAdmin(admin.ModelAdmin):
    list_display = ['user', 'widget_type', 'title', 'is_visible', 'created_at']
    list_filter = ['widget_type', 'is_visible']
    search_fields = ['user__email', 'title']


@admin.register(WidgetLayout)
class WidgetLayoutAdmin(admin.ModelAdmin):
    list_display = ['user', 'columns', 'updated_at']
    search_fields = ['user__email']
