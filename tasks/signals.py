from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from django.db import transaction
import time
from .models import Task

def clear_workspace_analytics_cache(workspace_id):
    """
    Clears all cached analytics patterns for a workspace.
    Uses versioning to avoid expensive keys() lookups where possible.
    """
    version_key = f"workspace_analytics_version_{workspace_id}"
    new_version = int(time.time() * 1000)
    cache.set(version_key, new_version, 86400 * 7) # Keep version for 7 days
    
    # We rely on versioning for high-traffic scalability.
    # Pattern-based deletion (keys() + delete_many()) is O(N) and can block Redis 
    # if millions of keys exist. Bumping the version effectively hides all old data.
        
    print(f"[CACHE] Workspace {workspace_id} analytics cleared (New v{new_version})")

@receiver([post_save, post_delete], sender=Task)
def task_saved_handler(sender, instance, **kwargs):
    """
    Signal receiver to clear workspace analytics cache when a task is created, updated or deleted.
    """
    workspace_id = instance.workspace_id
    # We clear the cache IMMEDIATELY after the transaction commits
    transaction.on_commit(lambda: clear_workspace_analytics_cache(workspace_id))
