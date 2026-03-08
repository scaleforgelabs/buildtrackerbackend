from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import ModuleAccess, ModulePreferences

@receiver([post_save, post_delete], sender=ModuleAccess)
def invalidate_module_access_cache(sender, instance, **kwargs):
    """Clear module access cache when new access is recorded"""
    user_id = instance.user.id
    workspace_id = instance.workspace.id if instance.workspace else None
    
    # Clear user-specific caches
    cache.delete_many(cache.keys(f"user_module_access_{user_id}_*"))
    
    # Clear workspace analytics caches
    if workspace_id:
        cache.delete_many(cache.keys(f"workspace_module_analytics_{workspace_id}_*"))

@receiver([post_save, post_delete], sender=ModulePreferences)
def invalidate_module_preferences_cache(sender, instance, **kwargs):
    """Clear module preferences cache when preferences change"""
    user_id = instance.user.id
    cache.delete(f"user_module_preferences_{user_id}")
