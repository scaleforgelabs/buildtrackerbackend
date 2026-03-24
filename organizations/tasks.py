from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
import secrets
import string
from core.messaging import send_dual_notification
from .models import Organization, OrganizationUsage, OrganizationInvitation

@shared_task
def calculate_organization_usage(organization_id):
    try:
        organization = Organization.objects.get(id=organization_id)
        usage, created = OrganizationUsage.objects.get_or_create(
            organization=organization,
            defaults={
                'user_count': 0,
                'workspace_count': 0,
                'storage_used_mb': 0,
                'file_count': 0
            }
        )
        
        usage.user_count = organization.member_count
        usage.save()
        
        return f"Usage calculated for organization {organization.name}"
    except Organization.DoesNotExist:
        return f"Organization {organization_id} not found"

@shared_task
def send_organization_invitation_email(invitation_id):
    try:
        invitation = OrganizationInvitation.objects.get(id=invitation_id)
        
        subject = f"Invitation to join {invitation.organization.name}"
        message = f"""
        You have been invited to join {invitation.organization.name} as a {invitation.role}.
        
        Click the link below to accept the invitation:
        {settings.FRONTEND_URL}/invitations/{invitation.token}
        
        This invitation will expire on {invitation.expires_at.strftime('%Y-%m-%d %H:%M:%S')}.
        """
        
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(email=invitation.email)
            send_dual_notification(user, subject, message, fail_silently=False)
        except User.DoesNotExist:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[invitation.email],
                fail_silently=False,
            )
        
        return f"Invitation notification sent to {invitation.email}"
    except OrganizationInvitation.DoesNotExist:
        return f"Invitation {invitation_id} not found"

@shared_task
def cleanup_expired_invitations():
    expired_invitations = OrganizationInvitation.objects.filter(
        status='pending',
        expires_at__lt=timezone.now()
    )
    
    count = expired_invitations.count()
    expired_invitations.update(status='expired')
    
    return f"Marked {count} invitations as expired"

@shared_task
def send_usage_alert_email(organization_id, usage_type, percentage):
    try:
        organization = Organization.objects.get(id=organization_id)
        
        subject = f"Usage Alert for {organization.name}"
        message = f"""
        Your organization "{organization.name}" has reached {percentage}% of its {usage_type} limit.
        
        Please consider upgrading your plan or managing your usage.
        
        Current plan: {organization.get_plan_type_display()}
        """
        
        if organization.owner:
            send_dual_notification(
                user=organization.owner,
                subject=subject,
                message=message,
                fail_silently=False,
            )
        
        return f"Usage alert sent to {organization.owner.email}"
    except Organization.DoesNotExist:
        return f"Organization {organization_id} not found"

@shared_task
def generate_invitation_token():
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(32))

@shared_task
def bulk_calculate_usage():
    organizations = Organization.objects.filter(is_active=True)
    count = 0
    
    for org in organizations:
        calculate_organization_usage.delay(str(org.id))
        count += 1
    
    return f"Queued usage calculation for {count} organizations"