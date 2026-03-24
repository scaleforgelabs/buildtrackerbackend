from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
import traceback
from core.messaging import send_dual_notification
from .models import Task, TaskComment
from django.utils.html import strip_tags

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
            
            Description: {strip_tags(task.task_description) if task.task_description else 'No description provided'}
            
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
        print(f"Error checking blockers: {traceback.format_exc()}")
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
def send_task_general_update_email(task_id, updated_fields, updater_name):
    try:
        task = Task.objects.get(id=task_id)
        
        subject = f"Task Updated: {task.task_name}"
        fields_str = ", ".join(updated_fields)
        message = f"""
        A task has been updated in {task.workspace.name} by {updater_name}.
        
        Task: {task.task_name}
        Updated Fields: {fields_str}
        
        View task: {settings.FRONTEND_URL}/{task.workspace.id}/tasks/{task.id}
        """
        
        if task.created_by:
            send_dual_notification(task.created_by, subject, message, fail_silently=True)
            
        if task.assigned_to and task.assigned_to != task.created_by:
            send_dual_notification(task.assigned_to, subject, message, fail_silently=True)
            
        return f"General update email sent for task {task.task_name}"
    except Task.DoesNotExist:
        return f"Task {task_id} not found"
    except Exception as e:
        return f"Error: {str(e)}"

@shared_task
def send_task_deletion_email(task_name, workspace_name, assigned_to_id, created_by_id, deleter_name):
    try:
        from auth_func.models import CustomUser
        
        subject = f"Task Deleted: {task_name}"
        message = f"""
        A task has been deleted in {workspace_name} by {deleter_name}.
        
        Task: {task_name}
        This task is no longer available.
        """
        
        try:
            creator = CustomUser.objects.get(id=created_by_id) if created_by_id else None
        except CustomUser.DoesNotExist:
            creator = None
            
        try:
            assignee = CustomUser.objects.get(id=assigned_to_id) if assigned_to_id else None
        except CustomUser.DoesNotExist:
            assignee = None
        
        if creator:
            send_dual_notification(creator, subject, message, fail_silently=True)
            
        if assignee and assignee != creator:
            send_dual_notification(assignee, subject, message, fail_silently=True)
            
        return f"Deletion email sent for task {task_name}"
    except Exception:
        import traceback
        return f"Error: {traceback.format_exc()}"

@shared_task
def update_workspace_task_count(workspace_id):
    try:
        from workspaces.models import Workspace
        workspace = Workspace.objects.get(id=workspace_id)
        task_count = workspace.tasks.count()
        workspace.no_of_tickets = task_count
        workspace.save()
        
        return f"Updated task count for workspace {workspace.name}: {task_count}"
    except Exception:
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

@shared_task
def send_task_comment_notification(task_id, comment_id):
    try:
        from workspaces.models import WorkspaceMember
        from core.messaging import send_dual_notification
        
        task = Task.objects.get(id=task_id)
        comment = TaskComment.objects.get(id=comment_id)
        commenter = comment.user
        
        # Get workspace admins/owners
        admins = WorkspaceMember.objects.filter(
            workspace=task.workspace,
            role__in=['Owner', 'Admin']
        ).select_related('user')
        
        recipients = set()
        for admin in admins:
            if admin.user:
                recipients.add(admin.user)
                
        if task.assigned_to:
            recipients.add(task.assigned_to)
            
            
        if not recipients:
            return "No recipients"
            
        subject = f"New Comment on Task: {task.task_name}"
        message = f"""
        {commenter.first_name} left a new comment on a task in {task.workspace.name}.
        
        Task: {task.task_name}
        Comment: "{strip_tags(comment.comment_text)[:500]}{'...' if len(strip_tags(comment.comment_text)) > 500 else ''}"
        
        View task: {settings.FRONTEND_URL}/{task.workspace.id}/tasks/{task.id}
        """
        
        for user in recipients:
            log_msg = f"Triggering comment email for task {task.id} to {user.email}\n"
            print(log_msg, flush=True)
            with open('task_email_debug.log', 'a') as f:
                f.write(log_msg)
            
            # Send Email/SMS
            send_dual_notification(user, subject, message, fail_silently=False)
            
        return f"Comment notification sent to {len(recipients)} users"
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        print(error_msg, flush=True)
        return str(e)

@shared_task
def send_task_blocker_notification(task_id, blocker_reason, triggered_by_user_id):
    try:
        from django.contrib.auth import get_user_model
        from workspaces.models import WorkspaceMember
        from core.messaging import send_dual_notification
        
        User = get_user_model()
        task = Task.objects.get(id=task_id)
        
        trigger_user = None
        if triggered_by_user_id:
            try:
                trigger_user = User.objects.get(id=triggered_by_user_id)
            except User.DoesNotExist:
                pass
        
        # Get workspace admins/owners
        admins = WorkspaceMember.objects.filter(
            workspace=task.workspace,
            role__in=['Owner', 'Admin']
        ).select_related('user')
        
        recipients = set()
        for admin in admins:
            if admin.user:
                recipients.add(admin.user)
                
        if task.assigned_to:
            recipients.add(task.assigned_to)
            
            
        if not recipients:
            return "No recipients"
            
        subject = f"URGENT: Task Blocked - {task.task_name}"
        trigger_name = trigger_user.first_name if trigger_user else "Someone"
        message = f"""
        {trigger_name} has reported a blocker on a task in {task.workspace.name}.
        
        Task: {task.task_name}
        Blocker Reason: {blocker_reason or 'No reason provided'}
        
        Please review the task immediately: {settings.FRONTEND_URL}/{task.workspace.id}/tasks/{task.id}
        """
        
        for user in recipients:
            log_msg = f"Triggering blocker email for task {task.id} to {user.email}\n"
            print(log_msg, flush=True)
            with open('task_email_debug.log', 'a') as f:
                f.write(log_msg)
                
            send_dual_notification(user, subject, message, fail_silently=False)
            
        return f"Blocker notification sent to {len(recipients)} users"
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        print(error_msg, flush=True)
        return str(e)