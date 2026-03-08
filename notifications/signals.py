from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from tasks.models import Task, TaskComment
from workspaces.models import WorkspaceMember
from .models import Notification
from django.utils import timezone

@receiver(post_save, sender=Task)
def task_notification(sender, instance, created, **kwargs):
    """Create notification when task is created or updated"""
    task = instance
    if created:
        if task.assigned_to:
            Notification.objects.create(
                user=task.assigned_to,
                workspace=task.workspace,
                action=f'Task Assigned: {task.task_name}',
                description=f'You have been assigned to "{task.task_name}"',
                note_type='task_assigned',
                severity='info'
            )
        
        workspace_admins = WorkspaceMember.objects.filter(
            workspace=task.workspace,
            role__in=['Owner', 'Admin']
        ).exclude(user=task.created_by)
        
        for member in workspace_admins:
            if member.user != task.assigned_to:
                Notification.objects.create(
                    user=member.user,
                    workspace=task.workspace,
                    action=f'New Task Created: {task.task_name}',
                    description=f'{task.created_by.first_name or task.created_by.email} created a new task',
                    note_type='task_created',
                    severity='info'
                )
    else:
        if hasattr(task, '_old_assigned_to') and task._old_assigned_to != task.assigned_to_id:
            if task.assigned_to:
                Notification.objects.create(
                    user=task.assigned_to,
                    workspace=task.workspace,
                    action=f'Task Assigned: {task.task_name}',
                    description=f'You have been assigned to "{task.task_name}"',
                    note_type='task_assigned',
                    severity='info'
                )
        
        if hasattr(task, '_old_status') and task._old_status != task.status:
            if task.assigned_to:
                Notification.objects.create(
                    user=task.assigned_to,
                    workspace=task.workspace,
                    action=f'Task Status Updated: {task.task_name}',
                    description=f'Task status changed from {task._old_status} to {task.status}',
                    note_type='task_updated',
                    severity='info'
                )
        
        if task.has_blocker and hasattr(task, '_old_has_blocker') and not task._old_has_blocker:
            if task.assigned_to:
                Notification.objects.create(
                    user=task.assigned_to,
                    workspace=task.workspace,
                    action=f'Critical Issue: {task.task_name}',
                    description=f'Task has a blocker: {task.blocker_reason or "No reason provided"}',
                    note_type='task_blocker',
                    severity='error'
                )
            
            
            workspace_admins = WorkspaceMember.objects.filter(
                workspace=task.workspace,
                role__in=['Owner', 'Admin']
            ).exclude(user=task.assigned_to)
            
            for member in workspace_admins:
                Notification.objects.create(
                    user=member.user,
                    workspace=task.workspace,
                    action=f'Critical Issue: {task.task_name}',
                    description=f'Task has a blocker: {task.blocker_reason or "No reason provided"}',
                    note_type='task_blocker',
                    severity='error'
                )
        
        if task.end_date:
            days_until_deadline = (task.end_date - timezone.now().date()).days
            if 0 <= days_until_deadline <= 2 and task.assigned_to:
                Notification.objects.create(
                    user=task.assigned_to,
                    workspace=task.workspace,
                    action=f'Deadline Approaching: {task.task_name}',
                    description=f'Task is due in {days_until_deadline} day{"s" if days_until_deadline != 1 else ""}',
                    note_type='deadline_approaching',
                    severity='warning'
                )

@receiver(post_delete, sender=Task)
def task_deleted_notification(sender, instance, **kwargs):
    """Create notification when task is deleted"""
    task = instance
    
    
    if task.assigned_to:
        Notification.objects.create(
            user=task.assigned_to,
            workspace=task.workspace,
            action=f'Task Deleted: {task.task_name}',
            description=f'Task "{task.task_name}" has been deleted',
            note_type='task_deleted',
            severity='info'
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
                workspace=member.workspace,
                action='Team Update',
                description=f'New member joined your workspace: {member.user.first_name or member.user.email}',
                note_type='member_joined',
                severity='success'
            )
        
        
        Notification.objects.create(
            user=member.user,
            workspace=member.workspace,
            action='Welcome to Workspace',
            description=f'You have joined {member.workspace.name}',
            note_type='member_joined',
            severity='success'
        )

@receiver(post_save, sender=TaskComment)
def task_comment_notification(sender, instance, created, **kwargs):
    """Create notification when comment is added to task"""
    if created:
        comment = instance
        task = comment.task
        
        if task.assigned_to and task.assigned_to != comment.user:
            Notification.objects.create(
                user=task.assigned_to,
                workspace=task.workspace,
                action=f'New Comment: {task.task_name}',
                description=f'{comment.user.first_name or comment.user.email} commented on your task',
                note_type='task_comment',
                severity='info'
            )
