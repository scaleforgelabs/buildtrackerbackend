from celery import shared_task
from core.messaging import send_beautiful_email
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

        subject = f"You're invited to join {invitation.organization.name}"
        message = (
            f"You've been invited to join {invitation.organization.name} on BuildTracker. "
            f"Click the button below to accept your invitation and get started."
        )
        invite_url = f"{settings.FRONTEND_URL}/invitations/{invitation.token}"

        metadata_rows = [
            {'label': 'Organization', 'value': invitation.organization.name},
            {'label': 'Role',         'value': invitation.role.capitalize()},
            {'label': 'Expires',      'value': invitation.expires_at.strftime('%-d %b %Y at %H:%M')},
        ]

        extra_context = {
            'email_type':    'invitation',
            'metadata_rows': metadata_rows,
            'action_url':    invite_url,
            'action_text':   'Accept Invitation',
        }

        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(email=invitation.email)
            extra_context['recipient_name'] = user.first_name or user.email.split('@')[0]
            send_dual_notification(user, subject, message, fail_silently=False, extra_context=extra_context)
        except User.DoesNotExist:
            send_beautiful_email(
                subject=subject,
                message=message,
                recipient_list=[invitation.email],
                fail_silently=False,
                extra_context=extra_context,
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

        subject = f"Usage alert: {percentage}% of {usage_type} limit reached"
        message = (
            f"Your organization {organization.name} is approaching its {usage_type} limit. "
            f"Consider upgrading your plan or managing current usage to avoid disruption."
        )

        metadata_rows = [
            {'label': 'Organization', 'value': organization.name},
            {'label': 'Limit type',   'value': usage_type.replace('_', ' ').title()},
            {'label': 'Usage',        'value': f"{percentage}% used"},
            {'label': 'Current plan', 'value': organization.get_plan_type_display()},
        ]

        if organization.owner:
            extra_context = {
                'email_type':     'usage_alert',
                'recipient_name': organization.owner.first_name or organization.owner.email.split('@')[0],
                'metadata_rows':  metadata_rows,
                'action_url':     f"{settings.FRONTEND_URL}/settings/billing",
                'action_text':    'Manage Plan',
            }
            send_dual_notification(
                user=organization.owner,
                subject=subject,
                message=message,
                fail_silently=False,
                extra_context=extra_context,
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