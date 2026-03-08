from django.contrib import admin
from .models import Notification

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['action', 'user', 'workspace', 'severity', 'is_read', 'created_at']
    list_filter = ['severity', 'is_read', 'created_at']
    search_fields = ['action', 'description', 'user__email']
    readonly_fields = ['created_at', 'read_at']
