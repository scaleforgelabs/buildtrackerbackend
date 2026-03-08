from django.contrib import admin
from .models import WaitlistEntry

@admin.register(WaitlistEntry)
class WaitlistEntryAdmin(admin.ModelAdmin):
    list_display = ['email', 'created_at']
    list_filter = ['created_at']
    search_fields = ['email']
    readonly_fields = ['created_at']
    ordering = ['-created_at']