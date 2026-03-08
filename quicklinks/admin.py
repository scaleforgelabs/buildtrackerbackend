from django.contrib import admin
from .models import QuickLink, QuickLinkCategory, SharedQuickLink, RecentItem

@admin.register(QuickLink)
class QuickLinkAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'category', 'entity_type', 'is_pinned', 'sort_order', 'created_at']
    list_filter = ['entity_type', 'is_pinned', 'created_at']
    search_fields = ['title', 'user__email', 'category']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(QuickLinkCategory)
class QuickLinkCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'created_at']
    search_fields = ['name', 'user__email']

@admin.register(SharedQuickLink)
class SharedQuickLinkAdmin(admin.ModelAdmin):
    list_display = ['title', 'workspace', 'category', 'visibility', 'created_by', 'created_at']
    list_filter = ['visibility', 'created_at']
    search_fields = ['title', 'workspace__name', 'category']

@admin.register(RecentItem)
class RecentItemAdmin(admin.ModelAdmin):
    list_display = ['user', 'item_type', 'item_id', 'action', 'access_count', 'last_accessed']
    list_filter = ['item_type', 'action', 'last_accessed']
    search_fields = ['user__email', 'item_id']