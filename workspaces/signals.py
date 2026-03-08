from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import WorkspaceSettings, WorkspaceMember, Workspace
from utils import invalidate_user_cache

@receiver([post_save, post_delete], sender=WorkspaceSettings)
def invalidate_workspace_settings_cache(sender, instance, **kwargs):
    """Clear workspace settings cache when settings are modified"""
    workspace_id = instance.workspace.id
    
    # Clear all user-specific settings caches for this workspace
    cache.delete_many(cache.keys(f"workspace_settings_{workspace_id}_*"))

@receiver([post_save, post_delete], sender=WorkspaceMember)
def invalidate_workspace_settings_cache_member(sender, instance, **kwargs):
    """Clear workspace settings cache when member roles change (affects permissions)"""
    workspace_id = instance.workspace.id
    user_id = instance.user.id
    
    # Clear specific user's settings cache
    cache.delete(f"workspace_settings_{workspace_id}_{user_id}")
    
    # Invalidate workspace owner's usage cache
    invalidate_user_cache(instance.workspace.owner)

@receiver([post_save, post_delete], sender=Workspace)
def invalidate_workspace_owner_cache(sender, instance, **kwargs):
    """Clear workspace owner's usage cache when workspace is created/deleted/modified"""
    invalidate_user_cache(instance.owner)