from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import secrets
import string
from core.messaging import send_dual_notification
from .models import Workspace, WorkspaceMember, WorkspaceInvitation

@shared_task
def send_workspace_creation_email(workspace_id):
    try:
        workspace = Workspace.objects.get(id=workspace_id)
        
        subject = f"Workspace '{workspace.name}' has been created"
        message = f"""
        Your workspace '{workspace.name}' has been successfully created.
        
        Workspace Details:
        - Name: {workspace.name}
        - Type: {workspace.type}
        - Description: {workspace.description or 'No description provided'}
        
        You can now start inviting members and managing your workspace.
        """
        
        send_dual_notification(
            user=workspace.owner,
            subject=subject,
            message=message,
            fail_silently=False,
        )
        
        return f"Workspace creation notification sent to {workspace.owner.email}"
    except Workspace.DoesNotExist:
        return f"Workspace {workspace_id} not found"

@shared_task
def send_workspace_invitation_email(invitation_id):
    try:
        invitation = WorkspaceInvitation.objects.get(id=invitation_id)
        
        subject = f"Invitation to join {invitation.workspace.name}"
        message = f"""
        You have been invited to join {invitation.workspace.name} as a {invitation.role}.
        
        Click the link below to accept the invitation:
        {settings.FRONTEND_URL}/workspace-invitations/{invitation.token}
        
        This invitation will expire on {invitation.expires_at.strftime('%Y-%m-%d %H:%M:%S')}.
        """
        
        # Invitation might not have a user object yet if they aren't registered
        # But maybe we should check if a user with that email already exists
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
    except WorkspaceInvitation.DoesNotExist:
        return f"Invitation {invitation_id} not found"

@shared_task
def send_workspace_member_removed_email(user_id, workspace_id, workspace_name, removed_by_email):
    """Send notification to a user when they are removed from a workspace."""
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.get(id=user_id)

        subject = f"You have been removed from '{workspace_name}'"
        message = f"""
        Hi {user.first_name or user.email},

        You have been removed from the workspace '{workspace_name}' by {removed_by_email}.

        If you believe this was a mistake, please contact your workspace administrator.

        — The BuildTracker Team
        """

        send_dual_notification(user, subject, message, fail_silently=True)

        return f"Member removal notification sent to {user.email}"
    except Exception as e:
        return f"Failed to send removal notification: {str(e)}"

@shared_task
def cleanup_expired_workspace_invitations():
    expired_invitations = WorkspaceInvitation.objects.filter(
        status='pending',
        expires_at__lt=timezone.now()
    )
    
    count = expired_invitations.count()
    expired_invitations.update(status='expired')
    
    return f"Marked {count} workspace invitations as expired"

@shared_task
def update_workspace_ticket_count(workspace_id):
    try:
        workspace = Workspace.objects.get(id=workspace_id)
        ticket_count = workspace.tasks.count() if hasattr(workspace, 'tasks') else 0
        workspace.no_of_tickets = ticket_count
        workspace.save()
        
        return f"Updated ticket count for workspace {workspace.name}: {ticket_count}"
    except Workspace.DoesNotExist:
        return f"Workspace {workspace_id} not found"