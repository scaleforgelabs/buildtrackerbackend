from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework import status, permissions
from rest_framework.decorators import permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count
from django.utils import timezone
from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from datetime import datetime, timedelta
from cachalot.api import cachalot_disabled

from django.db.models.functions import TruncDate
from workspaces.models import Workspace, WorkspaceMember
from tasks.models import Task
from waitlist.models import WaitlistEntry
from django.contrib.auth import get_user_model
from utils import check_workspace_permission, cache_lock

def get_dashboard_stats(workspace, date_from=None, date_to=None, milestone=None, sprint=None, bypass_cache=False):
    # DIRECT DB QUERIES for top-level stats to ensure 100% sync
    tasks = Task.objects.filter(workspace=workspace)
    
    if date_from:
        tasks = tasks.filter(created_at__date__gte=date_from)
    if date_to:
        tasks = tasks.filter(created_at__date__lte=date_to)
    if milestone:
        tasks = tasks.filter(milestone=milestone)
    if sprint:
        tasks = tasks.filter(sprint=sprint)
    
    total_tasks = tasks.count()
    completed_tasks = tasks.filter(status='completed').count()
    in_progress_tasks = tasks.filter(status='in_progress').count()
    overdue_tasks = tasks.filter(end_date__lt=timezone.now(), status__in=['pending', 'in_progress']).count()
    blocked_tasks = tasks.filter(has_blocker=True).count()
    
    total_members = WorkspaceMember.objects.filter(workspace=workspace).count()
    
    velocity = round(completed_tasks / max(total_tasks, 1), 2) if total_tasks > 0 else 0
    
    total = max(total_tasks, 1)
    # Standard Health Score Formula: (Completed + InProgress*0.6)/Total - (Overdue*0.4 + Blocked*0.4)/Total
    positive_impact = (completed_tasks + (in_progress_tasks * 0.6)) / total
    negative_impact = ((overdue_tasks * 0.4) + (blocked_tasks * 0.4)) / total
    health_score = max(0, min(100, round((positive_impact - negative_impact) * 100, 1)))
    
    milestone_progress = []
    if milestone:
        milestone_tasks = tasks.filter(milestone=milestone)
        milestone_completed = milestone_tasks.filter(status='completed').count()
        milestone_total = milestone_tasks.count()
        milestone_progress.append({
            'milestone_id': milestone,
            'total_tasks': milestone_total,
            'completed_tasks': milestone_completed,
            'progress_percentage': (milestone_completed / max(milestone_total, 1)) * 100
        })
    
    sprint_progress = []
    if sprint:
        sprint_tasks = tasks.filter(sprint=sprint)
        sprint_completed = sprint_tasks.filter(status='completed').count()
        sprint_total = sprint_tasks.count()
        sprint_progress.append({
            'sprint_id': sprint,
            'total_tasks': sprint_total,
            'completed_tasks': sprint_completed,
            'progress_percentage': (sprint_completed / max(sprint_total, 1)) * 100
        })
    
    stats = {
        'totalTasks': total_tasks,
        'completedTasks': completed_tasks,
        'inProgressTasks': in_progress_tasks,
        'pendingTasks': total_tasks - completed_tasks - in_progress_tasks, # Added pending count
        'overdueTasks': overdue_tasks,
        'blockedTasks': blocked_tasks,
        'totalMembers': total_members,
        'velocity': velocity,
        'healthScore': health_score,
        'milestoneProgress': milestone_progress,
        'sprintProgress': sprint_progress
    }
    
    # No cache.set - fresh every time
    return stats
    return stats

def get_dashboard_charts(workspace, period='monthly', milestone=None, date_from=None, date_to=None, bypass_cache=False):
    # Fresh charts: Removing manual cache for exact sync
    tasks = Task.objects.filter(workspace=workspace)
    if date_from:
        tasks = tasks.filter(created_at__date__gte=date_from)
    if date_to:
        tasks = tasks.filter(created_at__date__lte=date_to)
    if milestone:
        tasks = tasks.filter(milestone=milestone)
    
    status_data = list(tasks.values('status').annotate(count=Count('id')))
    status_chart = [{'label': (item['status'] or 'pending').lower(), 'value': item['count']} for item in status_data]
    
    priority_data = list(tasks.values('priority').annotate(count=Count('id')))
    priority_chart = [{'label': (item['priority'] or 'medium').lower(), 'value': item['count']} for item in priority_data]
    
    end_date = date_to if date_to else timezone.now().date()
    start_date = date_from if date_from else (end_date - timedelta(days=30))
    trend_data = []
    
    if (end_date - start_date).days > 365:
        start_date = end_date - timedelta(days=365)

    current_date = start_date
    completed_counts = dict(
        tasks.filter(
            status='completed',
            updated_at__date__gte=start_date,
            updated_at__date__lte=end_date
        )
        .annotate(date=TruncDate('updated_at'))
        .values('date')
        .annotate(count=Count('id'))
        .values_list('date', 'count')
    )
    
    while current_date <= end_date:
        daily_completed = completed_counts.get(current_date, 0)
        trend_data.append({
            'date': current_date,
            'label': current_date.strftime('%Y-%m-%d'),
            'value': daily_completed
        })
        current_date += timedelta(days=1)
    
    member_performance = []
    members = WorkspaceMember.objects.filter(workspace=workspace).select_related('user')
    
    user_stats = {}
    tasks_assigned_counts = tasks.values('assigned_to').annotate(
        total=Count('id'),
        completed=Count('id', filter=Q(status='completed')),
        pending=Count('id', filter=Q(status='pending')),
        in_progress=Count('id', filter=Q(status='in_progress')),
        overdue=Count('id', filter=Q(end_date__lt=timezone.now(), status__in=['pending', 'in_progress']))
    )
    for stat in tasks_assigned_counts:
        user_stats[stat['assigned_to']] = stat

    completed_task_times = tasks.filter(
        status='completed', created_at__isnull=False, updated_at__isnull=False, assigned_to__isnull=False
    ).values('assigned_to', 'created_at', 'updated_at')
    
    user_times = {}
    for t in completed_task_times:
        uid = t['assigned_to']
        duration = (t['updated_at'] - t['created_at']).total_seconds() / 86400
        if uid not in user_times:
            user_times[uid] = {'total': 0, 'count': 0}
        user_times[uid]['total'] += duration
        user_times[uid]['count'] += 1
        
    for member in members:
        uid = member.user.id
        stats = user_stats.get(uid, {})
        tasks_assigned = stats.get('total', 0)
        completed = stats.get('completed', 0)
        pending = stats.get('pending', 0)
        in_progress = stats.get('in_progress', 0)
        overdue = stats.get('overdue', 0)
        
        time_data = user_times.get(uid, {})
        avg_time = round(time_data['total'] / time_data['count'], 1) if time_data.get('count', 0) > 0 else 0
        
        efficiency = (completed / max(tasks_assigned, 1)) * 100
        
        first = member.user.first_name or ""
        last = member.user.last_name or ""
        full_name = f"{first} {last}".strip()
        display_name = full_name if full_name else member.user.email.split('@')[0]

        member_performance.append({
            'member_name': display_name,
            'member_first_name': member.user.first_name,
            'member_last_name': member.user.last_name,
            'member_email': member.user.email,
            'member_avatar': member.user.avatar.url if member.user.avatar else None,
            'member_phone': member.phone,
            'member_job_role': member.job_role,
            'member_role': member.role,
            'tasks_assigned': tasks_assigned,
            'tasks_completed': completed,
            'tasks_pending': pending,
            'tasks_in_progress': in_progress,
            'tasks_overdue': overdue,
            'avg_completion_time': avg_time,
            'efficiency_score': round(efficiency, 1)
        })

    active_member_ids = set(members.values_list('user_id', flat=True))
    unassigned_total = 0
    unassigned_completed = 0
    unassigned_pending = 0
    unassigned_in_progress = 0
    unassigned_overdue = 0
    
    for uid, u_stats in user_stats.items():
        if uid not in active_member_ids:
            unassigned_total += u_stats.get('total', 0)
            unassigned_completed += u_stats.get('completed', 0)
            unassigned_pending += u_stats.get('pending', 0)
            unassigned_in_progress += u_stats.get('in_progress', 0)
            unassigned_overdue += u_stats.get('overdue', 0)

    if unassigned_total > 0:
        unassigned_rate = (unassigned_completed / max(unassigned_total, 1)) * 100
        
        member_performance.append({
            'member_name': 'Unassigned / Former Members',
            'member_first_name': 'Unassigned',
            'member_last_name': 'Tasks',
            'member_email': 'N/A',
            'member_avatar': None,
            'member_phone': '',
            'member_job_role': 'N/A',
            'member_role': 'N/A',
            'tasks_assigned': unassigned_total,
            'tasks_completed': unassigned_completed,
            'tasks_pending': unassigned_pending,
            'tasks_in_progress': unassigned_in_progress,
            'tasks_overdue': unassigned_overdue,
            'avg_completion_time': 0,
            'efficiency_score': round(unassigned_rate, 1)
        })
    
    charts = {
        'statusData': status_chart,
        'priorityData': priority_chart,
        'trendData': trend_data,
        'memberPerformance': member_performance,
        'milestoneChart': [],
        'sprintChart': []
    }
    
    # No cache.set to maintain real-time accuracy across dashboard and report
    return charts

def get_performance_analytics(workspace, date_from=None, date_to=None, bypass_cache=False):
    # Guaranteed fresh analytics for the report page
    tasks = Task.objects.filter(workspace=workspace)
    if date_from:
        tasks = tasks.filter(created_at__date__gte=date_from)
    if date_to:
        tasks = tasks.filter(created_at__date__lte=date_to)
    
    total_tasks = tasks.count()
    completed_tasks = tasks.filter(status='completed').count()
    completion_rate = (completed_tasks / max(total_tasks, 1)) * 100
    
    completed_with_dates = tasks.filter(
        status='completed',
        created_at__isnull=False,
        updated_at__isnull=False
    )
    
    if completed_with_dates.exists():
        total_time = sum(
            (task.updated_at - task.created_at).total_seconds() / 86400
            for task in completed_with_dates
        )
        average_task_time = round(total_time / completed_with_dates.count(), 1)
    else:
        average_task_time = 0
    
    blocked_tasks = tasks.filter(has_blocker=True).count()
    blocked_rate = (blocked_tasks / max(total_tasks, 1)) * 100
    team_efficiency = round(max(0, completion_rate - blocked_rate), 1)
    
    bottlenecks = []
    # Return actual individual blocked tasks with their names and blocker reasons
    blocked_tasks_qs = tasks.filter(has_blocker=True).values('task_name', 'blocker_reason', 'priority', 'ticket_number')
    for bt in blocked_tasks_qs:
        bottlenecks.append({
            'area': bt['task_name'],
            'severity': bt.get('priority', 'medium'),
            'description': bt['blocker_reason'] or 'No reason specified',
            'impact_score': 0,
            'ticket_number': bt.get('ticket_number'),
        })
    
    milestone_metrics = []
    milestones = tasks.values('milestone').distinct()
    for milestone_data in milestones:
        if milestone_data['milestone']:
            milestone_tasks = tasks.filter(milestone=milestone_data['milestone'])
            milestone_completed = milestone_tasks.filter(status='completed').count()
            milestone_total = milestone_tasks.count()
            
            milestone_metrics.append({
                'milestone_id': milestone_data['milestone'],
                'milestone_name': f"Milestone {milestone_data['milestone']}",
                'completion_rate': (milestone_completed / max(milestone_total, 1)) * 100,
                'on_track': milestone_completed / max(milestone_total, 1) > 0.7,
                'estimated_completion': timezone.now().date() + timedelta(days=30)
            })
    
    sprint_metrics = []
    sprints = tasks.values('sprint').distinct()
    for sprint_data in sprints:
        if sprint_data['sprint']:
            sprint_tasks = tasks.filter(sprint=sprint_data['sprint'])
            sprint_completed = sprint_tasks.filter(status='completed').count()
            sprint_total = sprint_tasks.count()
            sprint_in_progress = sprint_tasks.filter(status='in_progress').count()
            
            s_completion_rate = (sprint_completed / max(sprint_total, 1)) * 100
            burndown_rate = (sprint_completed + sprint_in_progress) / max(sprint_total, 1)
            
            sprint_metrics.append({
                'sprint_id': sprint_data['sprint'],
                'sprint_name': f"Sprint {sprint_data['sprint']}",
                'velocity': sprint_completed,
                'burndown_rate': round(burndown_rate, 2),
                'completion_rate': s_completion_rate
            })
    
    analytics = {
        'completionRate': completion_rate,
        'averageTaskTime': average_task_time,
        'teamEfficiency': team_efficiency,
        'bottlenecks': bottlenecks,
        'milestoneMetrics': milestone_metrics,
        'sprintMetrics': sprint_metrics
    }
    
    # No cache.set to maintain absolute sync
    return analytics
    return analytics

def get_trends_analytics(workspace, period='weekly', date_from=None, date_to=None, bypass_cache=False):
    version_key = f"workspace_analytics_version_{workspace.id}"
    version = cache.get(version_key, 1)
    
    cache_key = f"trends_analytics_{workspace.id}_{period}_{date_from}_{date_to}_v{version}"
    if not bypass_cache:
        cached_data = cache.get(cache_key)
        if cached_data:
            return cached_data
            
    lock_key = cache_key + "_lock"
    with cache_lock(lock_key):
        if not bypass_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                return cached_data
            
        tasks = Task.objects.filter(workspace=workspace)
    
        if date_from:
            tasks = tasks.filter(created_at__date__gte=date_from)
        if date_to:
            tasks = tasks.filter(created_at__date__lte=date_to)
    
    end_date = date_to if date_to else timezone.now().date()
    
    if period == 'weekly':
        start_date = date_from if date_from else (end_date - timedelta(weeks=12))
        delta = timedelta(weeks=1)
    elif period == 'monthly':
        start_date = date_from if date_from else (end_date - timedelta(days=365))
        delta = timedelta(days=30)
    else:
        start_date = date_from if date_from else (end_date - timedelta(days=30))
        delta = timedelta(days=1)
    
    if (end_date - start_date).days > 365:
        start_date = end_date - timedelta(days=365)
    
    task_creation_trend = []
    completion_trend = []
    velocity_trend = []
    milestone_trend = []
    
    prev_created = 0
    prev_completed = 0
    
    current_date = start_date
    
    created_counts = dict(
        tasks.filter(created_at__date__range=[start_date, end_date + delta])
        .annotate(date=TruncDate('created_at'))
        .values('date')
        .annotate(count=Count('id'))
        .values_list('date', 'count')
    )
    completed_counts = dict(
        tasks.filter(status='completed', updated_at__date__range=[start_date, end_date + delta])
        .annotate(date=TruncDate('updated_at'))
        .values('date')
        .annotate(count=Count('id'))
        .values_list('date', 'count')
    )
    milestone_completed_counts = dict(
        tasks.filter(status='completed', milestone__isnull=False, updated_at__date__range=[start_date, end_date + delta])
        .annotate(date=TruncDate('updated_at'))
        .values('date')
        .annotate(count=Count('id'))
        .values_list('date', 'count')
    )
    
    while current_date <= end_date:
        period_end = min(current_date + delta, end_date)
        
        created_count = sum(count for d, count in created_counts.items() if d and current_date <= d <= period_end)
        completed_count = sum(count for d, count in completed_counts.items() if d and current_date <= d <= period_end)
        milestone_completed = sum(count for d, count in milestone_completed_counts.items() if d and current_date <= d <= period_end)
        
        created_change = ((created_count - prev_created) / max(prev_created, 1)) * 100 if prev_created > 0 else 0
        completed_change = ((completed_count - prev_completed) / max(prev_completed, 1)) * 100 if prev_completed > 0 else 0
        
        task_creation_trend.append({
            'date': current_date,
            'value': created_count,
            'change_percentage': round(created_change, 1)
        })
        
        completion_trend.append({
            'date': current_date,
            'value': completed_count,
            'change_percentage': round(completed_change, 1)
        })
        
        velocity_trend.append({
            'date': current_date,
            'value': completed_count / 7 if period == 'weekly' else completed_count,
            'change_percentage': round(completed_change, 1)
        })
        
        milestone_trend.append({
            'date': current_date,
            'value': milestone_completed,
            'change_percentage': round(completed_change, 1)
        })
        
        prev_created = created_count
        prev_completed = completed_count
        current_date = period_end + timedelta(days=1)
    
    trends = {
        'taskCreationTrend': task_creation_trend,
        'completionTrend': completion_trend,
        'velocityTrend': velocity_trend,
        'milestoneTrend': milestone_trend
    }
    
    if trends and not bypass_cache:
        cache.set(cache_key, trends, 300)
    return trends

@extend_schema(
    tags=["Analytics"],
    summary="Workspace Dashboard Stats",
    description="Get dashboard statistics for workspace",
    responses={200: {'description': 'Dashboard statistics'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def workspace_dashboard_stats(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        date_from = request.GET.get('DateFrom')
        date_to = request.GET.get('DateTo')
        milestone = request.GET.get('Milestone')
        sprint = request.GET.get('Sprint')

        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            except ValueError:
                date_from = None

        if date_to:
            try:
                date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            except ValueError:
                date_to = None

        if milestone:
            try:
                milestone = int(milestone)
            except ValueError:
                milestone = None

        if sprint:
            try:
                sprint = int(sprint)
            except ValueError:
                sprint = None

        bypass_cache = bool(request.GET.get('_t')) or request.GET.get('BypassCache') == 'true'
        
        with cachalot_disabled():
            stats = get_dashboard_stats(workspace, date_from, date_to, milestone, sprint, bypass_cache=bypass_cache)

        response = Response(stats)
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response

    return await _sync_logic()

@extend_schema(
    tags=["Analytics"],
    summary="Workspace Dashboard Charts",
    description="Get chart data for workspace dashboard",
    responses={200: {'description': 'Dashboard chart data'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def workspace_dashboard_charts(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        period = request.GET.get('Period', 'monthly')
        milestone = request.GET.get('Milestone')
        date_from = request.GET.get('DateFrom')
        date_to = request.GET.get('DateTo')


        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            except ValueError:
                date_from = None

        if date_to:
            try:
                date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            except ValueError:
                date_to = None

        if milestone:
            try:
                milestone = int(milestone)
            except ValueError:
                milestone = None

        bypass_cache = bool(request.GET.get('_t')) or request.GET.get('BypassCache') == 'true'

        with cachalot_disabled():
            charts = get_dashboard_charts(workspace, period, milestone, date_from, date_to, bypass_cache=bypass_cache)

        response = Response(charts)
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response

    return await _sync_logic()

@extend_schema(
    tags=["Analytics"],
    summary="Workspace Performance Analytics",
    description="Get performance analytics for workspace",
    responses={200: {'description': 'Performance analytics data'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def workspace_analytics_performance(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        date_from = request.GET.get('DateFrom')
        date_to = request.GET.get('DateTo')


        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            except ValueError:
                date_from = None

        if date_to:
            try:
                date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            except ValueError:
                date_to = None

        bypass_cache = bool(request.GET.get('_t')) or request.GET.get('BypassCache') == 'true'

        with cachalot_disabled():
            analytics = get_performance_analytics(workspace, date_from, date_to, bypass_cache=bypass_cache)

        response = Response(analytics)
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response

    return await _sync_logic()

@extend_schema(
    tags=["Analytics"],
    summary="Workspace Trends Analytics",
    description="Get trend analytics for workspace",
    responses={200: {'description': 'Trends analytics data'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def workspace_analytics_trends(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        period = request.GET.get('Period', 'weekly')
        date_from = request.GET.get('DateFrom')
        date_to = request.GET.get('DateTo')


        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            except ValueError:
                date_from = None

        if date_to:
            try:
                date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            except ValueError:
                date_to = None

        bypass_cache = bool(request.GET.get('_t')) or request.GET.get('BypassCache') == 'true'

        with cachalot_disabled():
            trends = get_trends_analytics(workspace, period, date_from, date_to, bypass_cache=bypass_cache)

        response = Response(trends)
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response
    return await _sync_logic()


@extend_schema(
    tags=["Analytics"],
    summary="Public Global Stats",
    description="Get global statistics like total workspaces and waitlist entries for marketing homepage",
    responses={200: {'description': 'Global statistics'}}
)
@api_view(['GET'])
@permission_classes([permissions.AllowAny])
async def public_stats(request):
    @sync_to_async
    def _get_counts():
        # Get custom user model
        User = get_user_model()
        
        # Count active workspaces
        workspace_count = Workspace.objects.filter(status='active').count()
        
        # Count actual users registered on the platform
        user_count = User.objects.count()
        
        # Count waitlist entries
        waitlist_count = WaitlistEntry.objects.count()
        
        # Total signups = Registered Users + Waitlist Entries
        # This provides a more accurate representation for "Global Signups"
        total_signups = user_count + waitlist_count
        
        return {
            'workspace_count': workspace_count,
            'waitlist_count': total_signups
        }
    
    counts = await _get_counts()
    return Response(counts)

