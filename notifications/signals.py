from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from tasks.models import Task, TaskComment
from workspaces.models import WorkspaceMember
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
                from notifications.tasks import notify_recipients
                notify_recipients(
                    recipient_ids=[str(task.assigned_to_id)],
                    workspace_id=task.workspace_id,
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
        
        # Notify existing workspace members via bulk Celery task
        existing_member_ids = list(
            WorkspaceMember.objects.filter(
                workspace=member.workspace
            ).exclude(user=member.user).values_list('user_id', flat=True)
        )
        
        from notifications.tasks import notify_recipients
        
        if existing_member_ids:
            notify_recipients(
                recipient_ids=existing_member_ids,
                workspace_id=member.workspace_id,
                action='Team Update',
                description=f'New member joined your workspace: {member.user.first_name or member.user.email}',
                note_type='member_joined',
                severity='success',
                triggered_by_id=member.user_id
            )
        
        # Welcome notification to the new member
        notify_recipients(
            recipient_ids=[str(member.user_id)],
            workspace_id=member.workspace_id,
            action='Welcome to Workspace',
            description=f'You have joined {member.workspace.name}',
            note_type='member_joined',
            severity='success',
            triggered_by_id=member.user_id
        )
