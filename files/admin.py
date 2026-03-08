from django.contrib import admin
from .models import File, Folder

@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = ['file_name', 'file_type', 'file_size', 'folder', 'workspace', 'uploaded_by', 'uploaded_at']
    list_filter = ['file_type', 'uploaded_at', 'folder']
    search_fields = ['file_name', 'uploaded_by__email']
    readonly_fields = ['uploaded_at', 'file_size', 'file_type']

@admin.register(Folder)
class FolderAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'workspace', 'created_by', 'created_at']
    list_filter = ['created_at', 'workspace']
    search_fields = ['name', 'created_by__email']