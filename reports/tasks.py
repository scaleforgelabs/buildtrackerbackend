from celery import shared_task
from django.utils import timezone
from django.core.cache import cache
from django.db.models import Q, Count, Avg
from .models import Report
from workspaces.models import WorkspaceMember
from tasks.models import Task

def generate_report_data(report_type, workspace, parameters):
    """Generate report data based on type and parameters"""
    cache_key = f"report_data_{report_type}_{workspace.id}_{hash(str(sorted(parameters.items())))}"
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data
    
    data = {}
    
    if report_type == 'task_summary':
        tasks = Task.objects.filter(workspace=workspace)
        if parameters.get('date_from'):
            tasks = tasks.filter(created_at__gte=parameters['date_from'])
        if parameters.get('date_to'):
            tasks = tasks.filter(created_at__lte=parameters['date_to'])
        
        aggs = tasks.aggregate(
            total=Count('id'),
            completed=Count('id', filter=Q(status='completed')),
            in_progress=Count('id', filter=Q(status='in_progress')),
            pending=Count('id', filter=Q(status='pending')),
        )
        
        data = {
            'total_tasks': aggs['total'] or 0,
            'completed_tasks': aggs['completed'] or 0,
            'in_progress_tasks': aggs['in_progress'] or 0,
            'pending_tasks': aggs['pending'] or 0,
            'tasks_by_priority': list(tasks.values('priority').annotate(count=Count('id'))),
            'tasks_by_assignee': list(tasks.values('assigned_to__email').annotate(count=Count('id'))),
        }
    
    elif report_type == 'user_performance':
        user_ids = parameters.get('user_ids', [])
        tasks = Task.objects.filter(workspace=workspace)
        if user_ids:
            tasks = tasks.filter(assigned_to__id__in=user_ids)
        
        data = {
            'user_stats': list(tasks.values('assigned_to__email').annotate(
                total_tasks=Count('id'),
                completed_tasks=Count('id', filter=Q(status='completed')),
                avg_completion_time=Avg('updated_at') - Avg('created_at')
            )),
        }
    
    elif report_type == 'workspace_overview':
        data = {
            'total_members': WorkspaceMember.objects.filter(workspace=workspace).count(),
            'total_tasks': Task.objects.filter(workspace=workspace).count(),
            'active_tasks': Task.objects.filter(workspace=workspace, status__in=['pending', 'in_progress']).count(),
            'completion_rate': Task.objects.filter(workspace=workspace, status='completed').count() / max(Task.objects.filter(workspace=workspace).count(), 1) * 100,
        }
    
    cache.set(cache_key, data, 900)
    return data

def generate_personal_report_data(report_type, user, workspace, parameters):
    """Generate personal report data for a user within a workspace"""
    cache_key = f"personal_report_{report_type}_{user.id}_{workspace.id}_{hash(str(sorted(parameters.items())))}"
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data
    
    data = {}
    tasks = Task.objects.filter(assigned_to=user, workspace=workspace)
    
    if report_type == 'personal_performance':
        recent_tasks = tasks.order_by('-updated_at')[:10]
        recent_activity = [{
            'task_name': task.task_name,
            'status': task.status,
            'updated_at': task.updated_at.isoformat()
        } for task in recent_tasks]
        
        data = {
            'total_tasks': tasks.count(),
            'completed_tasks': tasks.filter(status='completed').count(),
            'completion_rate': tasks.filter(status='completed').count() / max(tasks.count(), 1) * 100,
            'tasks_by_status': list(tasks.values('status').annotate(count=Count('id'))),
            'recent_activity': recent_activity,
        }
    
    cache.set(cache_key, data, 900)
    return data

@shared_task
def generate_workspace_report_task(report_id):
    try:
        report = Report.objects.get(id=report_id)
        report.status = 'processing'
        report.save()

        report_data = generate_report_data(report.report_type, report.workspace, report.parameters)
        
        report.data = report_data
        report.status = 'completed'
        report.completed_at = timezone.now()
        report.save()
    except Report.DoesNotExist:
        pass
    except Exception:
        report = Report.objects.get(id=report_id)
        report.status = 'failed'
        report.save()

@shared_task
def generate_personal_report_task(report_id):
    try:
        report = Report.objects.get(id=report_id)
        report.status = 'processing'
        report.save()

        report_data = generate_personal_report_data(report.report_type, report.user, report.workspace, report.parameters)
        
        report.data = report_data
        report.status = 'completed'
        report.completed_at = timezone.now()
        report.save()
    except Report.DoesNotExist:
        pass
    except Exception:
        report = Report.objects.get(id=report_id)
        report.status = 'failed'
        report.save()
