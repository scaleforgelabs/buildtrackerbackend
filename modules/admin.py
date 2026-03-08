from django.contrib import admin
from .models import ModuleAccess, ModulePreferences

@admin.register(ModuleAccess)
class ModuleAccessAdmin(admin.ModelAdmin):
    list_display = ['user', 'module_name', 'workspace', 'session_duration', 'accessed_at']
    list_filter = ['module_name', 'accessed_at']
    search_fields = ['user__email', 'module_name']
    readonly_fields = ['accessed_at']

@admin.register(ModulePreferences)
class ModulePreferencesAdmin(admin.ModelAdmin):
    list_display = ['user', 'quick_access_enabled', 'updated_at']
    search_fields = ['user__email']
    readonly_fields = ['created_at', 'updated_at']
