from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from django.db import transaction
import time
from .models import Task
from workspaces.models import WorkspaceMember, WorkspaceSettings
from reports.models import Report

def clear_workspace_analytics_cache(workspace_id):
    """
    Increments the version of a workspace's analytics cache, 
    effectively invalidating all cached analytics for that workspace.
    """
    version_key = f"workspace_analytics_version_{workspace_id}"
    new_version = int(time.time()) # Use a timestamp to ensure uniqueness and freshness
    cache.set(version_key, new_version, 86400 * 7) # Keep the version valid for 7 days
    print(f"DEBUG: Invalidated analytics for workspace {workspace_id}. New version: {new_version}")

@receiver(post_save, sender=Task)
def task_saved_handler(sender, instance, **kwargs):
    transaction.on_commit(lambda: clear_workspace_analytics_cache(instance.workspace_id))

@receiver(post_delete, sender=Task)
def task_deleted_handler(sender, instance, **kwargs):
    transaction.on_commit(lambda: clear_workspace_analytics_cache(instance.workspace_id))

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
