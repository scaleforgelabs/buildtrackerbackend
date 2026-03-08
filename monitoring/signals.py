from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import SystemMetric, SystemAlert, UsageMetric
from workspaces.models import Workspace
from tasks.models import Task
from files.models import File

@receiver([post_save, post_delete], sender=SystemMetric)
def invalidate_system_metrics_cache(sender, instance, **kwargs):
    """Clear system metrics cache when new metrics are added"""
    cache.delete("system_performance_metrics")
    cache.delete("service_health_status")

@receiver([post_save, post_delete], sender=SystemAlert)
def invalidate_alerts_cache(sender, instance, **kwargs):
    """Clear alerts cache when alerts change"""
    cache.delete_many(cache.keys("system_alerts_*"))

@receiver([post_save, post_delete], sender=UsageMetric)
def invalidate_usage_cache(sender, instance, **kwargs):
    """Clear usage cache when usage metrics change"""
    pass


@receiver([post_save, post_delete], sender=Workspace)
def invalidate_org_usage_cache_workspace(sender, instance, **kwargs):
    """Clear organization usage cache when workspaces change"""
    if instance.owner:
        cache.delete(f"user_usage_{instance.owner.id}")

@receiver([post_save, post_delete], sender=Task)
def invalidate_org_usage_cache_task(sender, instance, **kwargs):
    """Clear organization usage cache when tasks change"""
    if instance.workspace and instance.workspace.owner:
        cache.delete(f"user_usage_{instance.workspace.owner.id}")

@receiver([post_save, post_delete], sender=File)
def invalidate_org_usage_cache_file(sender, instance, **kwargs):
    """Clear organization usage cache when files change"""
    if instance.workspace and instance.workspace.owner:
        cache.delete(f"user_usage_{instance.workspace.owner.id}")