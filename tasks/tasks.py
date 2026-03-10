from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import traceback
import sys
from core.messaging import send_dual_notification
from .models import Task, TaskComment

@shared_task
def send_task_assignment_email(task_id):
    try:
        task = Task.objects.get(id=task_id)
        
        if task.assigned_to:
            subject = f"Task Assigned: {task.task_name}"
            message = f"""
            You have been assigned a new task in {task.workspace.name}.
            
            Task: {task.task_name}
            Priority: {task.get_priority_display()}
            Due Date: {task.end_date or 'Not set'}
            
            Description: {task.task_description or 'No description provided'}
            
            View task: {settings.FRONTEND_URL}/{task.workspace.id}/tasks/{task.id}
            """
            
            send_dual_notification(
                user=task.assigned_to,
                subject=subject,
                message=message,
                fail_silently=False
            )
        
        return f"Assignment email sent for task {task.task_name}"
    except Task.DoesNotExist:
        return f"Task {task_id} not found"
    except Exception as e:
        return f"Error: {str(e)}"

@shared_task
def send_task_status_update_email(task_id, old_status, new_status):
    try:
        task = Task.objects.get(id=task_id)
        recipients = []
        if task.created_by:
            recipients.append(task.created_by.email)
        if task.assigned_to and task.assigned_to != task.created_by:
            recipients.append(task.assigned_to.email)
        
        if recipients:
            subject = f"Task Status Updated: {task.task_name}"
            message = f"""
            Task status has been updated in {task.workspace.name}.
            
            Task: {task.task_name}
            Status changed from: {old_status} → {new_status}
            Progress: {task.percent_complete}%
            
            View task: {settings.FRONTEND_URL}/{task.workspace.id}/tasks/{task.id}
            """
            
            if task.created_by:
                send_dual_notification(task.created_by, subject, message, fail_silently=True)
            
            if task.assigned_to and task.assigned_to != task.created_by:
                send_dual_notification(task.assigned_to, subject, message, fail_silently=True)
        
        return f"Status update email sent for task {task.task_name}"
    except Task.DoesNotExist:
        return f"Task {task_id} not found"
    except Exception as e:
        error_trace = traceback.format_exc()
        return f"Error: {str(e)}"

@shared_task
def send_task_due_reminder_email(task_id):
    try:
        task = Task.objects.get(id=task_id)
        
        if task.assigned_to and task.end_date:
            subject = f"Task Due Reminder: {task.task_name}"
            message = f"""
            Reminder: Your task is due soon.
            
            Task: {task.task_name}
            Due Date: {task.end_date}
            Priority: {task.get_priority_display()}
            Progress: {task.percent_complete}%
            
            View task: {settings.FRONTEND_URL}/{task.workspace.id}/tasks/{task.id}
            """
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[task.assigned_to.email],
                fail_silently=False,
            )
        
        return f"Due reminder sent for task {task.task_name}"
    except Task.DoesNotExist:
        return f"Task {task_id} not found"

@shared_task
def update_workspace_task_count(workspace_id):
    try:
        from workspaces.models import Workspace
        workspace = Workspace.objects.get(id=workspace_id)
        task_count = workspace.tasks.count()
        workspace.no_of_tickets = task_count
        workspace.save()
        
        return f"Updated task count for workspace {workspace.name}: {task_count}"
    except:
        return f"Failed to update task count for workspace {workspace_id}"

@shared_task
def send_daily_task_summary():
    from django.contrib.auth import get_user_model
    from django.db.models import Count, Q
    User = get_user_model()
    
    users_with_stats = User.objects.annotate(
        pending_count=Count('assigned_tasks', filter=Q(assigned_tasks__status='pending')),
        in_progress_count=Count('assigned_tasks', filter=Q(assigned_tasks__status='in_progress')),
        overdue_count=Count('assigned_tasks', filter=Q(
            assigned_tasks__status__in=['pending', 'in_progress'],
            assigned_tasks__end_date__lt=timezone.now().date()
        ))
    ).filter(
        Q(pending_count__gt=0) | Q(in_progress_count__gt=0) | Q(overdue_count__gt=0)
    )
    
    for user in users_with_stats:
        pending_tasks = user.pending_count
        in_progress_tasks = user.in_progress_count
        overdue_tasks = user.overdue_count
        
        subject = "Daily Task Summary"
        message = f"""
        Your daily task summary:
        
        Pending Tasks: {pending_tasks}
        In Progress Tasks: {in_progress_tasks}
        Overdue Tasks: {overdue_tasks}
        
        Please review your tasks and update their status.
        """
        
        send_dual_notification(
            user=user,
            subject=subject,
            message=message,
            fail_silently=True,
        )
    
    return f"Daily summary sent to {users_with_stats.count()} users"