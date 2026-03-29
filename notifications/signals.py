from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from tasks.models import Task, TaskComment
from workspaces.models import WorkspaceMember
from .models import Notification
from django.utils import timezone

@receiver(post_save, sender=Task)
def task_notification(sender, instance, created, **kwargs):
    """Monitor task for approaching deadlines or other specific passive signals"""
    task = instance
    if not created:
        if task.end_date:
            task_end_date = task.end_date.date() if hasattr(task.end_date, 'date') else task.end_date
            days_until_deadline = (task_end_date - timezone.now().date()).days
            if 0 <= days_until_deadline <= 2 and task.assigned_to:
                Notification.objects.create(
                    user=task.assigned_to,
                    workspace=task.workspace,
                    action=f'Deadline Approaching: {task.task_name}',
                    description=f'Task is due in {days_until_deadline} day{"s" if days_until_deadline != 1 else ""}',
                    note_type='deadline_approaching',
                    severity='warning'
                )

@receiver(post_save, sender=WorkspaceMember)
def workspace_member_notification(sender, instance, created, **kwargs):
    """Create notification when new member joins workspace"""
    if created:
        member = instance
        
        
        existing_members = WorkspaceMember.objects.filter(
            workspace=member.workspace
        ).exclude(user=member.user)
        
        for existing_member in existing_members:
            Notification.objects.create(
                user=existing_member.user,
                triggered_by=member.user,
                workspace=member.workspace,
                action='Team Update',
                description=f'New member joined your workspace: {member.user.first_name or member.user.email}',
                note_type='member_joined',
                severity='success'
            )
        
        
        Notification.objects.create(
            user=member.user,
            triggered_by=member.user,
            workspace=member.workspace,
            action='Welcome to Workspace',
            description=f'You have joined {member.workspace.name}',
            note_type='member_joined',
            severity='success'
        )

