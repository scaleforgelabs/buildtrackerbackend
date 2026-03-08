from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from tasks.models import Task
from workspaces.models import WorkspaceMember

@receiver([post_save, post_delete], sender=Task)
def invalidate_analytics_cache(sender, instance, **kwargs):
    """Clear analytics cache when tasks are modified"""
    workspace_id = instance.workspace.id
    
    # Clear dashboard and analytics caches
    cache_patterns = [
        f"dashboard_stats_{workspace_id}_*",
        f"dashboard_charts_{workspace_id}_*",
        f"performance_analytics_{workspace_id}_*",
        f"trends_analytics_{workspace_id}_*",
    ]
    
    for pattern in cache_patterns:
        cache.delete_many(cache.keys(pattern))

@receiver([post_save, post_delete], sender=WorkspaceMember)
def invalidate_dashboard_cache_member(sender, instance, **kwargs):
    """Clear dashboard cache when workspace members change"""
    workspace_id = instance.workspace.id
    cache.delete_many(cache.keys(f"dashboard_stats_{workspace_id}_*"))
    cache.delete_many(cache.keys(f"dashboard_charts_{workspace_id}_*"))