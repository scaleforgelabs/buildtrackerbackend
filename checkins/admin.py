from django.contrib import admin
from .models import DailyCheckIn, CheckInBlocker


class CheckInBlockerInline(admin.TabularInline):
    model = CheckInBlocker
    extra = 0
    readonly_fields = ('id', 'created_at')


@admin.register(DailyCheckIn)
class DailyCheckInAdmin(admin.ModelAdmin):
    list_display = ('user', 'workspace', 'sentiment', 'has_blockers', 'date', 'created_at')
    list_filter = ('sentiment', 'has_blockers', 'date', 'workspace')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'workspace__name')
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [CheckInBlockerInline]


@admin.register(CheckInBlocker)
class CheckInBlockerAdmin(admin.ModelAdmin):
    list_display = ('checkin', 'priority', 'notify_member', 'created_at')
    list_filter = ('priority',)
    readonly_fields = ('id', 'created_at')
