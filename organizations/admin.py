from django.contrib import admin
from .models import Organization, OrganizationMembership, OrganizationUsage, OrganizationInvitation

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'plan_type', 'member_count', 'created_at', 'is_active']
    list_filter = ['plan_type', 'is_active', 'created_at']
    search_fields = ['name', 'owner__email', 'billing_email']
    readonly_fields = ['id', 'created_at', 'updated_at', 'member_count']
    
    @admin.display(
        description='Members'
    )
    def member_count(self, obj):
        return obj.member_count

@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'organization', 'role', 'joined_at', 'is_active']
    list_filter = ['role', 'is_active', 'joined_at']
    search_fields = ['user__email', 'organization__name']
    readonly_fields = ['id', 'joined_at']

@admin.register(OrganizationUsage)
class OrganizationUsageAdmin(admin.ModelAdmin):
    list_display = ['organization', 'user_count', 'workspace_count', 'storage_used_mb', 'last_calculated']
    list_filter = ['last_calculated']
    search_fields = ['organization__name']
    readonly_fields = ['id', 'last_calculated']

@admin.register(OrganizationInvitation)
class OrganizationInvitationAdmin(admin.ModelAdmin):
    list_display = ['email', 'organization', 'role', 'status', 'created_at', 'expires_at']
    list_filter = ['role', 'status', 'created_at']
    search_fields = ['email', 'organization__name']
    readonly_fields = ['id', 'token', 'created_at']