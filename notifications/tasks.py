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
    
    for task in tasks:
        days_until_deadline = (task.end_date - today).days
        
        
        existing_notification = Notification.objects.filter(
            user=task.assigned_to,
            workspace=task.workspace,
            note_type='deadline_approaching',
            created_at__date=today,
            action__icontains=task.task_name
        ).exists()
        
        if not existing_notification and task.assigned_to:
            Notification.objects.create(
                user=task.assigned_to,
                workspace=task.workspace,
                action=f'Deadline Approaching: {task.task_name}',
                description=f'Task is due in {days_until_deadline} day{"s" if days_until_deadline != 1 else ""}',
                note_type='deadline_approaching',
                severity='warning'
            )

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
