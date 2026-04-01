from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import Task
from workspaces.models import WorkspaceMember, WorkspaceSettings
from reports.models import Report

def clear_workspace_analytics_cache(workspace_id):
 
    version_key = f"workspace_analytics_version_{workspace_id}"
    try:
        cache.incr(version_key)
    except (ValueError, TypeError, Exception):
        # Set to 2 because 1 is the default value in the analytics view.
        # This ensures the cache key changes immediately.
        cache.set(version_key, 2, 86400)
    
    print(f"Invalidated analytics cache for workspace {workspace_id}")

@receiver(post_save, sender=Task)
def task_saved_handler(sender, instance, **kwargs):
    clear_workspace_analytics_cache(instance.workspace_id)

@receiver(post_delete, sender=Task)
def task_deleted_handler(sender, instance, **kwargs):
    clear_workspace_analytics_cache(instance.workspace_id)

@receiver(post_save, sender=WorkspaceMember)
def member_saved_handler(sender, instance, **kwargs):
    clear_workspace_analytics_cache(instance.workspace_id)

@receiver(post_delete, sender=WorkspaceMember)
def member_deleted_handler(sender, instance, **kwargs):
    clear_workspace_analytics_cache(instance.workspace_id)

@receiver(post_save, sender=WorkspaceSettings)
def settings_saved_handler(sender, instance, **kwargs):
    clear_workspace_analytics_cache(instance.workspace_id)

@receiver(post_save, sender=Report)
def report_saved_handler(sender, instance, **kwargs):
    clear_workspace_analytics_cache(instance.workspace_id)

@receiver(post_delete, sender=Report)
def report_deleted_handler(sender, instance, **kwargs):
    clear_workspace_analytics_cache(instance.workspace_id)
