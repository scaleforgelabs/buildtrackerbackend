from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from tasks.models import Task
from workspaces.models import WorkspaceMember
from .models import Notification

@shared_task
def check_approaching_deadlines():
    """Check for tasks with approaching deadlines and create notifications"""
    today = timezone.now().date()
    two_days_later = today + timedelta(days=2)
    
    
    tasks = Task.objects.filter(
        end_date__gte=today,
        end_date__lte=two_days_later,
        status__in=['pending', 'in_progress']
    ).select_related('assigned_to', 'workspace')
    
    # Optimization: Fetch all existing deadline notifications for today in one query
    existing_notifications = set(
        Notification.objects.filter(
            note_type='deadline_approaching',
            created_at__date=today
        ).values_list('user_id', 'workspace_id', 'action', flat=False)
    )
    
    notifications_to_create = []
    
    for task in tasks:
        days_until_deadline = (task.end_date - today).days
        action_str = f'Deadline Approaching: {task.task_name}'
        
        # Check against the pre-fetched set (User, Workspace, Action string)
        if (task.assigned_to_id, task.workspace_id, action_str) not in existing_notifications and task.assigned_to:
            notifications_to_create.append(
                Notification(
                    user=task.assigned_to,
                    workspace=task.workspace,
                    action=action_str,
                    description=f'Task is due in {days_until_deadline} day{"s" if days_until_deadline != 1 else ""}',
                    note_type='deadline_approaching',
                    severity='warning'
                )
            )
    
    if notifications_to_create:
        Notification.objects.bulk_create(notifications_to_create)

@shared_task
def send_daily_task_summary():
    """Send daily summary of tasks to workspace members"""
    
    workspaces = WorkspaceMember.objects.values_list('workspace', flat=True).distinct()
    
    for workspace_id in workspaces:
        
        tasks_updated = Task.objects.filter(
            workspace_id=workspace_id,
            updated_at__date=timezone.now().date()
        ).count()
        
        tasks_completed = Task.objects.filter(
            workspace_id=workspace_id,
            status='completed',
            updated_at__date=timezone.now().date()
        ).count()
        
        if tasks_updated > 0 or tasks_completed > 0:
            
            members = WorkspaceMember.objects.filter(workspace_id=workspace_id)
            
            for member in members:
                description = []
                if tasks_updated > 0:
                    description.append(f'{tasks_updated} task{"s" if tasks_updated != 1 else ""} updated')
                if tasks_completed > 0:
                    description.append(f'{tasks_completed} task{"s" if tasks_completed != 1 else ""} completed')
                
                Notification.objects.create(
                    user=member.user,
                    workspace_id=workspace_id,
                    action='Daily Task Summary',
                    description=', '.join(description),
                    note_type='daily_summary',
                    severity='info'
                )

@shared_task
def create_notification_task(user_id, workspace_id, action, description=None, note_type=None, severity='info', triggered_by_id=None):
    from auth_func.models import CustomUser
    from workspaces.models import Workspace
    from .models import Notification
    
    user = CustomUser.objects.get(id=user_id)
    workspace = Workspace.objects.get(id=workspace_id) if workspace_id else None
    triggered_by = CustomUser.objects.filter(id=triggered_by_id).first() if triggered_by_id else None
    
    if user:
        Notification.objects.create(
            user=user,
            triggered_by=triggered_by,
            workspace=workspace,
            action=action,
            description=description,
            note_type=note_type,
            severity=severity
        )


@shared_task
def create_notifications_batch_task(recipient_ids, workspace_id, action, description=None, note_type=None, severity='info', triggered_by_id=None):
    """Create notifications for multiple recipients in a single bulk INSERT.
    
    This replaces the anti-pattern of N individual Notification.objects.create()
    calls inside request handlers. One .delay() call → one bulk_create → done.
    """
    from auth_func.models import CustomUser
    from workspaces.models import Workspace
    from .models import Notification
    
    if not recipient_ids:
        return
    
    workspace = Workspace.objects.filter(id=workspace_id).first() if workspace_id else None
    triggered_by = CustomUser.objects.filter(id=triggered_by_id).first() if triggered_by_id else None
    
    # Deduplicate recipient IDs
    unique_ids = list(set(recipient_ids))
    
    notifications = [
        Notification(
            user_id=uid,
            triggered_by=triggered_by,
            workspace=workspace,
            action=action,
            description=description,
            note_type=note_type,
            severity=severity
        )
        for uid in unique_ids
    ]
    
    Notification.objects.bulk_create(notifications)


def notify_recipients(recipient_ids, workspace_id, action, description=None, note_type=None, severity='info', triggered_by_id=None):
    """Helper to dispatch notification creation to Celery.
    
    Call this from views instead of Notification.objects.create() loops.
    Accepts user IDs (as strings) to avoid passing Django model instances to Celery.
    """
    if not recipient_ids:
        return
    
    # Convert to strings for JSON serialization
    clean_ids = [str(uid) for uid in recipient_ids if uid]
    if clean_ids:
        create_notifications_batch_task.delay(
            clean_ids,
            str(workspace_id) if workspace_id else None,
            action,
            description,
            note_type,
            severity,
            str(triggered_by_id) if triggered_by_id else None
        )
