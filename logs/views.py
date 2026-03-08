from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework import status, permissions
from rest_framework.decorators import permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q, Avg, Max
from django.utils import timezone
from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from datetime import datetime, timedelta
import uuid

from django.db.models.functions import TruncDate
from .models import WorkspaceLog, AuditTrailLog, UserActivityLog, SystemEventLog
from .serializers import *
from workspaces.models import Workspace, WorkspaceMember
from utils import sanitize_input, check_workspace_permission

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'PageSize'
    max_page_size = 200
    page_query_param = 'Page'

def get_filtered_logs(queryset, request):
    log_type = request.GET.get('LogType')
    severity = request.GET.get('Severity')
    user_id = request.GET.get('UserId')
    date_from = request.GET.get('DateFrom')
    date_to = request.GET.get('DateTo')
    search_key = request.GET.get('SearchKey')
    sort_column = request.GET.get('SortColumn', 'created_at')
    sort_order = request.GET.get('SortOrder', 'desc')
    
    if log_type:
        queryset = queryset.filter(log_type=log_type)
    
    if severity:
        queryset = queryset.filter(severity=severity)
    
    if user_id:
        queryset = queryset.filter(user_id=user_id)
    
    if date_from:
        try:
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            queryset = queryset.filter(created_at__date__gte=date_from)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            queryset = queryset.filter(created_at__date__lte=date_to)
        except ValueError:
            pass
    
    if search_key:
        search_key = sanitize_input(search_key)
        from django.contrib.postgres.search import SearchQuery
        queryset = queryset.filter(
            Q(search_vector=SearchQuery(search_key)) |
            Q(entity_type__icontains=search_key)
        )
    
    order_prefix = '-' if sort_order == 'desc' else ''
    queryset = queryset.order_by(f"{order_prefix}{sort_column}")
    
    return queryset

def generate_log_summary(logs, date_from=None, date_to=None):
    cache_key = f"log_summary_{hash(str(logs.query))}_{date_from}_{date_to}"
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data
    
    total_actions = logs.count()
    unique_users = logs.values('user').distinct().count()
    error_logs = logs.filter(severity__in=['error', 'critical']).count()
    error_rate = (error_logs / max(total_actions, 1)) * 100
    
    
    most_active = logs.values('user__email', 'user__first_name', 'user__last_name').annotate(
        action_count=Count('id')
    ).order_by('-action_count').first()
    
    most_active_user = None
    if most_active:
        name = f"{most_active['user__first_name']} {most_active['user__last_name']}".strip()
        most_active_user = {
            'email': most_active['user__email'],
            'name': name or most_active['user__email'],
            'action_count': most_active['action_count']
        }
    
    summary = {
        'total_actions': total_actions,
        'unique_users': unique_users,
        'error_rate': round(error_rate, 2),
        'most_active_user': most_active_user
    }
    
    cache.set(cache_key, summary, 300)
    return summary

@extend_schema(
    tags=["Logs"],
    summary="Detailed Workspace Logs",
    description="Get detailed workspace logs with filtering and summary",
    responses={200: {'description': 'Detailed workspace logs'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def workspace_logs_detailed(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        logs = WorkspaceLog.objects.filter(workspace=workspace).select_related('user')
        filtered_logs = get_filtered_logs(logs, request)

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(filtered_logs, request)

        serializer = WorkspaceLogSerializer(page, many=True)


        log_summary = generate_log_summary(
            filtered_logs,
            request.GET.get('DateFrom'),
            request.GET.get('DateTo')
        )

        return Response({
            'data': serializer.data,
            'pagination': {
                'page': paginator.page.number,
                'page_size': paginator.page_size,
                'total_pages': paginator.page.paginator.num_pages,
                'total_count': paginator.page.paginator.count
            },
            'filters': {
                'log_type': request.GET.get('LogType', ''),
                'severity': request.GET.get('Severity', ''),
                'user_id': request.GET.get('UserId', ''),
                'search_key': request.GET.get('SearchKey', ''),
                'sort_column': request.GET.get('SortColumn', 'created_at'),
                'sort_order': request.GET.get('SortOrder', 'desc')
            },
            'log_summary': log_summary
        })

    return await _sync_logic()

@extend_schema(
    tags=["Logs"],
    summary="Activity Timeline",
    description="Get workspace activity timeline with daily summaries",
    responses={200: {'description': 'Activity timeline data'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def workspace_activity_timeline(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        date_from = request.GET.get('DateFrom')
        date_to = request.GET.get('DateTo')
        user_id = request.GET.get('UserId')

        cache_key = f"activity_timeline_{workspaceId}_{date_from}_{date_to}_{user_id}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)


        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            except ValueError:
                date_from = timezone.now().date() - timedelta(days=30)
        else:
            date_from = timezone.now().date() - timedelta(days=30)

        if date_to:
            try:
                date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            except ValueError:
                date_to = timezone.now().date()
        else:
            date_to = timezone.now().date()


        logs = WorkspaceLog.objects.filter(
            workspace=workspace,
            created_at__date__range=[date_from, date_to]
        ).select_related('user')

        if user_id:
            logs = logs.filter(user_id=user_id)


        timeline = []
        for log in logs.order_by('-created_at')[:100]:
            timeline.append({
                'timestamp': log.created_at,
                'action': log.action,
                'user': log.user.email if log.user else 'System',
                'description': log.description,
                'entity_type': log.entity_type,
                'severity': log.severity
            })


        action_counts = dict(
            logs.annotate(date=TruncDate('created_at'))
            .values('date')
            .annotate(count=Count('id'))
            .values_list('date', 'count')
        )

        unique_user_counts = dict(
            logs.annotate(date=TruncDate('created_at'))
            .values('date')
            .annotate(count=Count('user', distinct=True))
            .values_list('date', 'count')
        )

        error_counts = dict(
            logs.filter(severity__in=['error', 'critical'])
            .annotate(date=TruncDate('created_at'))
            .values('date')
            .annotate(count=Count('id'))
            .values_list('date', 'count')
        )

        hour_counts_data = logs.extra(select={'hour': 'EXTRACT(hour FROM created_at)'}).annotate(
            date=TruncDate('created_at')
        ).values('date', 'hour').annotate(count=Count('id'))

        peak_hours = {}
        day_hours = {}
        for hc in hour_counts_data:
            d = hc['date']
            h = hc['hour']
            c = hc['count']
            if d not in day_hours:
                day_hours[d] = {}
            day_hours[d][h] = c

        for d, hours in day_hours.items():
            peak_hours[d] = max(hours.items(), key=lambda x: x[1])[0]

        daily_summary = []
        current_date = date_from
        while current_date <= date_to:
            daily_summary.append({
                'date': current_date,
                'total_actions': action_counts.get(current_date, 0),
                'unique_users': unique_user_counts.get(current_date, 0),
                'error_count': error_counts.get(current_date, 0),
                'peak_hour': peak_hours.get(current_date, 0)
            })
            current_date += timedelta(days=1)


        peak_hours = []
        hour_counts = logs.extra(select={'hour': 'EXTRACT(hour FROM created_at)'}).values('hour').annotate(count=Count('id')).order_by('-count')[:5]
        total_actions = logs.count()

        for hour_data in hour_counts:
            peak_hours.append({
                'hour': hour_data['hour'],
                'activity_count': hour_data['count'],
                'percentage': (hour_data['count'] / max(total_actions, 1)) * 100
            })

        response_data = {
            'timeline': timeline,
            'daily_summary': daily_summary,
            'peak_hours': peak_hours
        }

        cache.set(cache_key, response_data, 600)
        return Response(response_data)

    return await _sync_logic()

@extend_schema(
    tags=["Logs"],
    summary="Audit Trail",
    description="Get audit trail logs with security events",
    responses={200: {'description': 'Audit trail data'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def workspace_audit_trail(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)


        if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
            return Response({'error': 'Only workspace owners and admins can view audit trails'}, status=status.HTTP_403_FORBIDDEN)

        action = request.GET.get('Action')
        entity_type = request.GET.get('EntityType')
        date_from = request.GET.get('DateFrom')

        audit_logs = AuditTrailLog.objects.filter(workspace=workspace).select_related('user')

        if action:
            audit_logs = audit_logs.filter(action=action)

        if entity_type:
            audit_logs = audit_logs.filter(entity_type=entity_type)

        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                audit_logs = audit_logs.filter(created_at__date__gte=date_from)
            except ValueError:
                pass

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(audit_logs, request)

        serializer = AuditTrailLogSerializer(page, many=True)


        security_events = []


        failed_logins = audit_logs.filter(action='failed_login')
        if failed_logins.exists():
            security_events.append({
                'event_type': 'failed_login',
                'severity': 'medium',
                'count': failed_logins.count(),
                'last_occurrence': failed_logins.order_by('-created_at').first().created_at
            })


        unauthorized = audit_logs.filter(action='unauthorized_access')
        if unauthorized.exists():
            security_events.append({
                'event_type': 'unauthorized_access',
                'severity': 'high',
                'count': unauthorized.count(),
                'last_occurrence': unauthorized.order_by('-created_at').first().created_at
            })

        return Response({
            'data': serializer.data,
            'pagination': {
                'page': paginator.page.number,
                'page_size': paginator.page_size,
                'total_pages': paginator.page.paginator.num_pages,
                'total_count': paginator.page.paginator.count
            },
            'security_events': security_events
        })
    return await _sync_logic()

@extend_schema(
    tags=["Logs"],
    summary="User Activity Logs",
    description="Get detailed user activity logs for workspace",
    responses={200: {'description': 'User activity data'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def workspace_user_activity(request, workspaceId, userId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
            return Response({'error': 'Only workspace owners and admins can view user activity'}, status=status.HTTP_403_FORBIDDEN)

        date_from = request.GET.get('DateFrom')
        date_to = request.GET.get('DateTo')

        cache_key = f"user_activity_{workspaceId}_{userId}_{date_from}_{date_to}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)


        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            except ValueError:
                date_from = timezone.now().date() - timedelta(days=30)
        else:
            date_from = timezone.now().date() - timedelta(days=30)

        if date_to:
            try:
                date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            except ValueError:
                date_to = timezone.now().date()
        else:
            date_to = timezone.now().date()


        user_activities = UserActivityLog.objects.filter(
            user_id=userId,
            workspace=workspace,
            created_at__date__range=[date_from, date_to]
        )


        total_sessions = user_activities.values('session_id').distinct().count()
        total_actions = user_activities.count()
        modules_accessed = list(user_activities.values_list('module', flat=True).distinct())


        peak_hour = user_activities.extra(
            select={'hour': 'EXTRACT(hour FROM created_at)'}
        ).values('hour').annotate(count=Count('id')).order_by('-count').first()

        peak_activity_time = f"{peak_hour['hour']}:00" if peak_hour else "N/A"

        activity_summary = {
            'total_sessions': total_sessions,
            'total_actions': total_actions,
            'modules_accessed': [m for m in modules_accessed if m],
            'peak_activity_time': peak_activity_time
        }


        completed_tasks = WorkspaceLog.objects.filter(
            workspace=workspace,
            user_id=userId,
            log_type='task_update',
            metadata__status='completed',
            created_at__date__range=[date_from, date_to]
        ).count()

        avg_duration = user_activities.aggregate(avg_duration=Avg('duration_ms'))['avg_duration'] or 0
        most_used = user_activities.values('module').annotate(count=Count('id')).order_by('-count').first()


        if total_actions > 0:
            completion_rate = (completed_tasks / total_actions) * 100
            session_efficiency = min(100, (avg_duration / 1000 / 60) if avg_duration > 0 else 0)
            efficiency_score = (completion_rate * 0.7) + (session_efficiency * 0.3)
        else:
            efficiency_score = 0

        productivity_metrics = {
            'tasks_completed': completed_tasks,
            'avg_session_duration': avg_duration,
            'most_used_feature': most_used['module'] if most_used else 'N/A',
            'efficiency_score': round(efficiency_score, 2)
        }

        serializer = UserActivityLogSerializer(user_activities[:100], many=True)

        response_data = {
            'user_activity': serializer.data,
            'activity_summary': activity_summary,
            'productivity_metrics': productivity_metrics
        }

        cache.set(cache_key, response_data, 600)
        return Response(response_data)

    return await _sync_logic()

@extend_schema(
    tags=["Logs"],
    summary="System Events",
    description="Get system event logs with health metrics",
    responses={200: {'description': 'System events data'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def workspace_system_events(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
            return Response({'error': 'Only workspace owners and admins can view system events'}, status=status.HTTP_403_FORBIDDEN)

        event_type = request.GET.get('EventType')
        severity = request.GET.get('Severity')
        date_from = request.GET.get('DateFrom')

        system_events = SystemEventLog.objects.filter(workspace=workspace)

        if event_type:
            system_events = system_events.filter(event_type=event_type)

        if severity:
            system_events = system_events.filter(severity=severity)

        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                system_events = system_events.filter(created_at__date__gte=date_from)
            except ValueError:
                pass

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(system_events, request)

        serializer = SystemEventLogSerializer(page, many=True)


        total_events = system_events.count()
        error_events = system_events.filter(event_type='error').count()
        critical_events = system_events.filter(severity='critical').count()


        from monitoring.models import SystemMetric
        response_time_metrics = SystemMetric.objects.filter(
            metric_name='response_time',
            timestamp__gte=timezone.now() - timedelta(hours=24)
        )
        avg_response_time = response_time_metrics.aggregate(Avg('value'))['value__avg'] or 0


        oldest_metric = SystemMetric.objects.order_by('timestamp').first()
        if oldest_metric:
            uptime_seconds = (timezone.now() - oldest_metric.timestamp).total_seconds()
            uptime_hours = uptime_seconds / 3600
            uptime_percentage = min(99.99, (uptime_hours / (uptime_hours + 0.01)) * 100)
        else:
            uptime_percentage = 0

        system_health = {
            'error_rate': round((error_events / max(total_events, 1)) * 100, 2),
            'critical_events': critical_events,
            'avg_response_time': round(avg_response_time, 2),
            'uptime_percentage': round(uptime_percentage, 2)
        }

        return Response({
            'data': serializer.data,
            'pagination': {
                'page': paginator.page.number,
                'page_size': paginator.page_size,
                'total_pages': paginator.page.paginator.num_pages,
                'total_count': paginator.page.paginator.count
            },
            'system_health': system_health
        })

    return await _sync_logic()

@extend_schema(
    tags=["Logs"],
    summary="Export Logs",
    description="Create export job for workspace logs",
    responses={201: {'description': 'Export job created'}}
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
async def workspace_logs_export(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
            return Response({'error': 'Only workspace owners and admins can export logs'}, status=status.HTTP_403_FORBIDDEN)

        serializer = LogExportSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        export_job_id = str(uuid.uuid4())


        estimated_completion = timezone.now() + timedelta(minutes=5)
        download_url = f"/api/files/exports/logs_{export_job_id}.{data['format']}"

        return Response({
            'export_job_id': export_job_id,
            'download_url': download_url,
            'estimated_completion': estimated_completion.isoformat()
        }, status=status.HTTP_201_CREATED)

    return await _sync_logic()

@extend_schema(
    tags=["Logs"],
    summary="User Activity Logs",
    description="Get personal activity logs for user",
    responses={200: {'description': 'Personal activity logs'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def user_activity_logs(request, userId):
    @sync_to_async
    def _sync_logic():

        if str(request.user.id) != userId and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        date_from = request.GET.get('DateFrom')
        workspace_id = request.GET.get('WorkspaceId')

        user_activities = UserActivityLog.objects.filter(user_id=userId)

        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                user_activities = user_activities.filter(created_at__date__gte=date_from)
            except ValueError:
                pass

        if workspace_id:
            user_activities = user_activities.filter(workspace_id=workspace_id)

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(user_activities, request)

        serializer = UserActivityLogSerializer(page, many=True)


        total_logins = user_activities.filter(activity_type='login').count()
        total_actions = user_activities.count()

        favorite_workspace = user_activities.values('workspace__name').annotate(
            count=Count('id')
        ).order_by('-count').first()

        most_active_day = user_activities.extra(
            select={'day': 'EXTRACT(dow FROM created_at)'}
        ).values('day').annotate(count=Count('id')).order_by('-count').first()

        days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

        personal_stats = {
            'total_logins': total_logins,
            'total_actions': total_actions,
            'favorite_workspace': favorite_workspace['workspace__name'] if favorite_workspace else 'N/A',
            'most_active_day': days[int(most_active_day['day'])] if most_active_day else 'N/A'
        }

        return Response({
            'data': serializer.data,
            'pagination': {
                'page': paginator.page.number,
                'page_size': paginator.page_size,
                'total_pages': paginator.page.paginator.num_pages,
                'total_count': paginator.page.paginator.count
            },
            'personal_stats': personal_stats
        })
    return await _sync_logic()

