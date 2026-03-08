from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Organization, OrganizationMembership, OrganizationUsage
from .tasks import calculate_organization_usage

@receiver(post_save, sender=OrganizationMembership)
def update_usage_on_membership_change(sender, instance, created, **kwargs):
    if created or instance.is_active:
        calculate_organization_usage.delay(str(instance.organization.id))

@receiver(post_delete, sender=OrganizationMembership)
def update_usage_on_membership_delete(sender, instance, **kwargs):
    calculate_organization_usage.delay(str(instance.organization.id))

@receiver(post_save, sender=Organization)
def create_organization_usage(sender, instance, created, **kwargs):
    if created:
        OrganizationUsage.objects.get_or_create(
            organization=instance,
            defaults={
                'user_count': 1,
                'workspace_count': 0,
                'storage_used_mb': 0,
                'file_count': 0
            }
        )