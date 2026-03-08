from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from tasks.models import Task
from workspaces.models import WorkspaceMember

@receiver([post_save, post_delete], sender=Task)
def invalidate_task_report_cache(sender, instance, **kwargs):
    """Clear report cache when tasks are modified"""
    workspace_id = instance.workspace.id
    user_id = instance.assigned_to.id if instance.assigned_to else None
    
    # Clear workspace report caches
    cache_patterns = [
        f"report_data_task_summary_{workspace_id}_*",
        f"report_data_user_performance_{workspace_id}_*",
        f"report_data_workspace_overview_{workspace_id}_*",
    ]
    
    for pattern in cache_patterns:
        cache.delete_many(cache.keys(pattern))
    
    # Clear personal report caches
    if user_id:
        personal_patterns = [
            f"personal_report_personal_performance_{user_id}_*",
            f"personal_report_task_history_{user_id}_*",
        ]
        for pattern in personal_patterns:
            cache.delete_many(cache.keys(pattern))

@receiver([post_save, post_delete], sender=WorkspaceMember)
def invalidate_workspace_report_cache(sender, instance, **kwargs):
    """Clear workspace overview cache when members change"""
    workspace_id = instance.workspace.id
    cache.delete_many(cache.keys(f"report_data_workspace_overview_{workspace_id}_*"))