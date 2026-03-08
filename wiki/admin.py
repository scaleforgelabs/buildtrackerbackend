from django.contrib import admin
from .models import WikiDocument, WikiDocumentAttachment

@admin.register(WikiDocument)
class WikiDocumentAdmin(admin.ModelAdmin):
    list_display = ['document_title', 'category', 'visibility', 'author', 'workspace', 'created_at']
    list_filter = ['visibility', 'category', 'created_at']
    search_fields = ['document_title', 'document_description', 'category']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(WikiDocumentAttachment)
class WikiDocumentAttachmentAdmin(admin.ModelAdmin):
    list_display = ['file_name', 'document', 'uploaded_by', 'uploaded_at']
    list_filter = ['uploaded_at']
    search_fields = ['file_name', 'document__document_title']