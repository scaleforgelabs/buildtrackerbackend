from celery import shared_task
from core.messaging import send_beautiful_email, send_dual_notification
from django.conf import settings
from django.utils import timezone
import traceback
from .models import Task, TaskComment
from django.utils.html import strip_tags


def _task_url(task):
    slug = getattr(task.workspace, 'slug', None) or str(task.workspace.id)
    return f"{settings.FRONTEND_URL}/{slug}/tasks/{task.ticket_number}"


def _fmt_date(d):
    if not d:
        return 'Not set'
    try:
        return d.strftime('%-d %b %Y') if hasattr(d, 'strftime') else str(d)
    except Exception:
        return str(d)


def _priority_label(p):
    return {'low': 'Low', 'medium': 'Medium', 'high': 'High'}.get(p, p.capitalize() if p else 'Medium')


def _status_label(s):
    return s.replace('_', ' ').title() if s else '—'


@shared_task
def update_task_search_vector(task_pk):
    """Update the search vector for a task asynchronously."""
    from django.contrib.postgres.search import SearchVector
    Task.objects.filter(pk=task_pk).update(
        search_vector=SearchVector('task_name', 'task_description')
    )


@shared_task
def send_task_assignment_email(task_id):
    try:
        task = Task.objects.select_related('assigned_to', 'workspace', 'created_by').get(id=task_id)
        if not task.assigned_to:
            return "No assignee"

        assignee = task.assigned_to
        subject = f"You've been assigned: {task.task_name}"

        message = (
            f"You have been assigned a new task in the {task.workspace.name} workspace. "
            f"Please review the details below and get started."
        )

        metadata_rows = [
            {'label': 'Task',      'value': task.task_name},
            {'label': 'Priority',  'value': _priority_label(task.priority)},
            {'label': 'Due Date',  'value': _fmt_date(task.end_date)},
            {'label': 'Workspace', 'value': task.workspace.name},
        ]
        if task.task_description:
            snippet = strip_tags(task.task_description)[:180]
            if snippet:
                metadata_rows.append({'label': 'Description', 'value': snippet + ('…' if len(strip_tags(task.task_description)) > 180 else '')})

        extra_context = {
            'email_type':     'task_assigned',
            'recipient_name': assignee.first_name or assignee.email.split('@')[0],
            'metadata_rows':  metadata_rows,
            'action_url':     _task_url(task),
            'action_text':    'View Task',
        }

        send_dual_notification(
            user=assignee,
            subject=subject,
            message=message,
            fail_silently=False,
            extra_context=extra_context,
        )
        return f"Assignment email sent for task {task.task_name}"
    except Task.DoesNotExist:
        return f"Task {task_id} not found"
    except Exception as e:
        return f"Error: {str(e)}"


@shared_task
def send_task_status_update_email(task_id, old_status, new_status):
    try:
        task = Task.objects.select_related('assigned_to', 'workspace', 'created_by').get(id=task_id)

        recipients = []
        if task.created_by:
            recipients.append(task.created_by)
        if task.assigned_to and task.assigned_to != task.created_by:
            recipients.append(task.assigned_to)

        if not recipients:
            return "No recipients"

        subject = f"Task status updated: {task.task_name}"
        message = f"The status of a task in {task.workspace.name} has changed."

        metadata_rows = [
            {'label': 'Task',       'value': task.task_name},
            {'label': 'Previous',   'value': _status_label(old_status)},
            {'label': 'New Status', 'value': _status_label(new_status)},
            {'label': 'Progress',   'value': f"{task.percent_complete}% complete"},
            {'label': 'Workspace',  'value': task.workspace.name},
        ]

        for user in recipients:
            extra_context = {
                'email_type':     'status_update',
                'recipient_name': user.first_name or user.email.split('@')[0],
                'metadata_rows':  metadata_rows,
                'action_url':     _task_url(task),
                'action_text':    'View Task',
            }
            send_dual_notification(user, subject, message, fail_silently=True, extra_context=extra_context)

        return f"Status update email sent for task {task.task_name}"
    except Task.DoesNotExist:
        return f"Task {task_id} not found"
    except Exception as e:
        print(f"Error sending status update email: {traceback.format_exc()}")
        return f"Error: {str(e)}"


@shared_task
def send_task_due_reminder_email(task_id):
    try:
        task = Task.objects.select_related('assigned_to', 'workspace').get(id=task_id)
        if not task.assigned_to or not task.end_date:
            return "No assignee or due date"

        assignee = task.assigned_to
        today = timezone.now().date()
        end = task.end_date.date() if hasattr(task.end_date, 'date') else task.end_date
        days_left = (end - today).days

        if days_left < 0:
            urgency = "This task is overdue."
        elif days_left == 0:
            urgency = "This task is due today."
        elif days_left == 1:
            urgency = "This task is due tomorrow."
        else:
            urgency = f"This task is due in {days_left} days."

        subject = f'Reminder: "{task.task_name}" is due soon'
        message = f"{urgency} Please review your progress and update the task status."

        metadata_rows = [
            {'label': 'Task',      'value': task.task_name},
            {'label': 'Due Date',  'value': _fmt_date(task.end_date)},
            {'label': 'Priority',  'value': _priority_label(task.priority)},
            {'label': 'Progress',  'value': f"{task.percent_complete}% complete"},
            {'label': 'Workspace', 'value': task.workspace.name},
        ]

        extra_context = {
            'email_type':     'reminder',
            'recipient_name': assignee.first_name or assignee.email.split('@')[0],
            'metadata_rows':  metadata_rows,
            'action_url':     _task_url(task),
            'action_text':    'Update Task Progress',
        }

        send_beautiful_email(
            subject=subject,
            message=message,
            recipient_list=[assignee.email],
            fail_silently=False,
            extra_context=extra_context,
        )
        return f"Due reminder sent for task {task.task_name}"
    except Task.DoesNotExist:
        return f"Task {task_id} not found"


@shared_task
def send_task_general_update_email(task_id, updated_fields, updater_name):
    try:
        task = Task.objects.select_related('assigned_to', 'workspace', 'created_by').get(id=task_id)

        fields_str = ', '.join(f.replace('_', ' ').title() for f in updated_fields)
        subject = f"Task updated: {task.task_name}"
        message = f"{updater_name} made changes to a task in {task.workspace.name}."

        metadata_rows = [
            {'label': 'Task',           'value': task.task_name},
            {'label': 'Updated by',     'value': updater_name},
            {'label': 'Fields changed', 'value': fields_str or 'General update'},
            {'label': 'Workspace',      'value': task.workspace.name},
        ]

        for user in filter(None, [task.created_by, task.assigned_to if task.assigned_to != task.created_by else None]):
            extra_context = {
                'email_type':     'general_update',
                'recipient_name': user.first_name or user.email.split('@')[0],
                'metadata_rows':  metadata_rows,
                'action_url':     _task_url(task),
                'action_text':    'View Task',
            }
            send_dual_notification(user, subject, message, fail_silently=True, extra_context=extra_context)

        return f"General update email sent for task {task.task_name}"
    except Task.DoesNotExist:
        return f"Task {task_id} not found"
    except Exception as e:
        return f"Error: {str(e)}"


@shared_task
def send_task_deletion_email(task_name, workspace_name, assigned_to_id, created_by_id, deleter_name):
    try:
        from auth_func.models import CustomUser

        subject = f"Task deleted: {task_name}"
        message = f"{deleter_name} deleted a task in {workspace_name}. The task is no longer available."

        metadata_rows = [
            {'label': 'Task',       'value': task_name},
            {'label': 'Deleted by', 'value': deleter_name},
            {'label': 'Workspace',  'value': workspace_name},
        ]

        for uid in filter(None, {created_by_id, assigned_to_id}):
            try:
                user = CustomUser.objects.get(id=uid)
            except CustomUser.DoesNotExist:
                continue
            extra_context = {
                'email_type':     'deletion',
                'recipient_name': user.first_name or user.email.split('@')[0],
                'metadata_rows':  metadata_rows,
            }
            send_dual_notification(user, subject, message, fail_silently=True, extra_context=extra_context)

        return f"Deletion email sent for task {task_name}"
    except Exception:
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
        subject = "Your daily task summary"
        message = "Here's a quick overview of your open tasks across all workspaces."

        metadata_rows = [
            {'label': 'Pending',     'value': str(user.pending_count)},
            {'label': 'In Progress', 'value': str(user.in_progress_count)},
            {'label': 'Overdue',     'value': str(user.overdue_count)},
        ]

        extra_context = {
            'email_type':     'daily_summary',
            'recipient_name': user.first_name or user.email.split('@')[0],
            'metadata_rows':  metadata_rows,
            'action_url':     f"{settings.FRONTEND_URL}",
            'action_text':    'Open BuildTracker',
        }

        send_dual_notification(
            user=user,
            subject=subject,
            message=message,
            fail_silently=True,
            extra_context=extra_context,
        )

    return f"Daily summary sent to {users_with_stats.count()} users"


@shared_task
def send_task_comment_notification(task_id, comment_id):
    try:
        from workspaces.models import WorkspaceMember

        task = Task.objects.select_related('workspace', 'assigned_to').get(id=task_id)
        comment = TaskComment.objects.select_related('user').get(id=comment_id)
        commenter = comment.user

        admins = WorkspaceMember.objects.filter(
            workspace=task.workspace,
            role__in=['Owner', 'Admin']
        ).select_related('user')

        recipients = {a.user for a in admins if a.user}
        if task.assigned_to:
            recipients.add(task.assigned_to)

        # Don't notify the commenter themselves
        recipients.discard(commenter)

        if not recipients:
            return "No recipients"

        comment_text = strip_tags(comment.comment_text)
        snippet = comment_text[:240] + ('…' if len(comment_text) > 240 else '')

        subject = f"New comment on: {task.task_name}"
        message = f"{commenter.first_name or commenter.email} left a comment on a task in {task.workspace.name}."

        metadata_rows = [
            {'label': 'Task',      'value': task.task_name},
            {'label': 'Comment',   'value': f'"{snippet}"'},
            {'label': 'By',        'value': f"{commenter.first_name} {commenter.last_name}".strip() or commenter.email},
            {'label': 'Workspace', 'value': task.workspace.name},
        ]

        for user in recipients:
            extra_context = {
                'email_type':     'comment',
                'recipient_name': user.first_name or user.email.split('@')[0],
                'metadata_rows':  metadata_rows,
                'action_url':     _task_url(task),
                'action_text':    'View Comment',
            }
            send_dual_notification(user, subject, message, fail_silently=False, extra_context=extra_context)

        return f"Comment notification sent to {len(recipients)} users"
    except Exception as e:
        print(traceback.format_exc(), flush=True)
        return str(e)


@shared_task
def send_task_blocker_notification(task_id, blocker_reason, triggered_by_user_id):
    try:
        from django.contrib.auth import get_user_model
        from workspaces.models import WorkspaceMember

        User = get_user_model()
        task = Task.objects.select_related('workspace', 'assigned_to').get(id=task_id)

        trigger_user = None
        if triggered_by_user_id:
            trigger_user = User.objects.filter(id=triggered_by_user_id).first()

        admins = WorkspaceMember.objects.filter(
            workspace=task.workspace,
            role__in=['Owner', 'Admin']
        ).select_related('user')

        recipients = {a.user for a in admins if a.user}
        if task.assigned_to:
            recipients.add(task.assigned_to)

        if not recipients:
            return "No recipients"

        trigger_name = (
            f"{trigger_user.first_name} {trigger_user.last_name}".strip()
            if trigger_user else "A team member"
        )
        subject = f"Blocker reported on: {task.task_name}"
        message = f"{trigger_name} has flagged a blocker on a task in {task.workspace.name}. Immediate attention may be required."

        metadata_rows = [
            {'label': 'Task',        'value': task.task_name},
            {'label': 'Reported by', 'value': trigger_name},
            {'label': 'Reason',      'value': blocker_reason or 'No reason provided'},
            {'label': 'Workspace',   'value': task.workspace.name},
        ]

        for user in recipients:
            extra_context = {
                'email_type':     'blocker',
                'recipient_name': user.first_name or user.email.split('@')[0],
                'metadata_rows':  metadata_rows,
                'action_url':     _task_url(task),
                'action_text':    'Review Blocker',
            }
            send_dual_notification(user, subject, message, fail_silently=False, extra_context=extra_context)

        return f"Blocker notification sent to {len(recipients)} users"
    except Exception as e:
        print(traceback.format_exc(), flush=True)
        return str(e)
