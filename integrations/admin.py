from django.contrib import admin
from .models import Integration

@admin.register(Integration)
class IntegrationAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'workspace', 'created_by', 'created_at']
    list_filter = ['category', 'created_at']
    search_fields = ['name', 'description', 'category']
    readonly_fields = ['created_at', 'updated_at']