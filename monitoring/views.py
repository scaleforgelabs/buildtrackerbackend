from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework import status, permissions
from rest_framework.decorators import permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Avg, Sum, Max
from django.utils import timezone
from django.core.cache import cache
from django.db import connection
from drf_spectacular.utils import extend_schema
from datetime import datetime, timedelta
import psutil
import time

from .models import SystemMetric, SystemAlert
from .serializers import (
    SystemMetricSerializer, SystemAlertSerializer
)
from workspaces.models import Workspace
from logs.models import UserActivityLog
from utils import check_workspace_permission

def check_admin_permission(user, workspace):
    """Check if user is workspace admin or owner"""
    return check_workspace_permission(user, workspace, ['Owner', 'Admin'])

def resolve_workspace(workspace_id_or_slug):
    import uuid
    try:
        val = uuid.UUID(str(workspace_id_or_slug))
        return get_object_or_404(Workspace, id=val)
    except ValueError:
        return get_object_or_404(Workspace, slug=workspace_id_or_slug)

def check_organization_access(user, user_id):
    """Check if user has access to another user's data (only themselves)"""
    return str(user.id) == str(user_id)

def get_system_performance_metrics():
    """Get current system performance metrics from database"""
    cache_key = "system_performance_metrics"
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data
    
    # Use interval=None for non-blocking call (returns CPU % since last call).
    # interval=1 was blocking the thread pool for 1 full second on every cache miss.
    cpu_usage = psutil.cpu_percent(interval=None)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE state = 'active';")
        db_connections = cursor.fetchone()[0]
    
    from .tasks import create_system_metrics_task
    metrics_list = [
        {'metric_type': 'performance', 'metric_name': 'cpu_usage', 'value': cpu_usage, 'unit': 'percent'},
        {'metric_type': 'performance', 'metric_name': 'memory_usage', 'value': memory.percent, 'unit': 'percent'},
        {'metric_type': 'performance', 'metric_name': 'disk_usage', 'value': disk.percent, 'unit': 'percent'},
        {'metric_type': 'performance', 'metric_name': 'database_connections', 'value': db_connections, 'unit': 'count'},
    ]
    create_system_metrics_task.delay(metrics_list)
    
    recent_metrics = SystemMetric.objects.filter(
        metric_name='cache_hit_rate',
        timestamp__gte=timezone.now() - timedelta(hours=1)
    )
    cache_hit_rate = recent_metrics.aggregate(Avg('value'))['value__avg'] or 0
    
    response_time_metrics = SystemMetric.objects.filter(
        metric_name='response_time',
        timestamp__gte=timezone.now() - timedelta(hours=1)
    )
    avg_response_time = response_time_metrics.aggregate(Avg('value'))['value__avg'] or 0
    
    metrics = {
        'cpu_usage': cpu_usage,
        'memory_usage': memory.percent,
        'disk_usage': disk.percent,
        'database_connections': db_connections,
        'cache_hit_rate': cache_hit_rate,
        'avg_response_time': avg_response_time
    }
    
    cache.set(cache_key, metrics, 30)
    return metrics

def get_service_health():
    """Check health of various services"""
    cache_key = "service_health_status"
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data
    
    services = []
    
    try:
        start_time = time.time()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
        db_response_time = (time.time() - start_time) * 1000
        
        services.append({
            'service_name': 'Database',
            'status': 'healthy' if db_response_time < 100 else 'degraded',
            'response_time': db_response_time,
            'last_check': timezone.now(),
            'details': {'connection_count': connection.queries.__len__()}
        })
    except Exception:
        services.append({
            'service_name': 'Database',
            'status': 'down',
            'response_time': 0,
            'last_check': timezone.now(),
            'details': {'error': 'Connection failed'}
        })
    
    try:
        start_time = time.time()
        cache.set('health_check', 'ok', 1)
        cache.get('health_check')
        cache_response_time = (time.time() - start_time) * 1000
        
        services.append({
            'service_name': 'Cache',
            'status': 'healthy' if cache_response_time < 50 else 'degraded',
            'response_time': cache_response_time,
            'last_check': timezone.now(),
            'details': {}
        })
    except Exception:
        services.append({
            'service_name': 'Cache',
            'status': 'down',
            'response_time': 0,
            'last_check': timezone.now(),
            'details': {'error': 'Cache unavailable'}
        })
    
    cache.set(cache_key, services, 60)
    return services

def calculate_system_status(services, performance_metrics):
    """Calculate overall system status"""
    down_services = [s for s in services if s['status'] == 'down']
    degraded_services = [s for s in services if s['status'] == 'degraded']
    
    if down_services:
        return 'down'
    elif degraded_services or performance_metrics['cpu_usage'] > 80 or performance_metrics['memory_usage'] > 85:
        return 'degraded'
    else:
        return 'healthy'

def get_organization_usage_data(user, date_from, date_to):
    """Get detailed usage data for user (organization)"""
    from organizations.user_org_views import calculate_user_stats
    cache_key = f"user_usage_{user.id}_{date_from}_{date_to}"
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data
    
    usage_data = calculate_user_stats(user)
    
    cache.set(cache_key, usage_data, 300)
    return usage_data

def get_usage_trends(user, date_from, date_to):
    """Get usage trends for user"""
    # UsageMetric model references old Organization model - disabled for User = Organization architecture
    return []

def get_cost_breakdown(user):
    """Get cost breakdown for user"""
    usage_data = get_organization_usage_data(user, timezone.now().date() - timedelta(days=30), timezone.now().date())
    
    user_cost = usage_data['user_count'] * 10
    storage_cost = usage_data['storage_used_mb'] / 1024 * 0.1
    total_cost = user_cost + storage_cost
    
    return [
        {
            'category': 'User Licenses',
            'amount': user_cost,
            'percentage': (user_cost / total_cost) * 100 if total_cost > 0 else 0
        },
        {
            'category': 'Storage',
            'amount': storage_cost,
            'percentage': (storage_cost / total_cost) * 100 if total_cost > 0 else 0
        }
    ]

def get_optimization_suggestions(user):
    """Get optimization suggestions for user"""
    usage_data = get_organization_usage_data(user, timezone.now().date() - timedelta(days=30), timezone.now().date())
    suggestions = []
    
    if usage_data['storage_used_mb'] > 5000:
        suggestions.append({
            'category': 'Storage',
            'suggestion': 'Consider implementing file compression or archiving old files',
            'potential_savings': usage_data['storage_used_mb'] * 0.1 * 0.3,
            'priority': 'medium'
        })
    
    return suggestions

@extend_schema(
    tags=["Monitoring"],
    summary="System Health Check",
    description="Get overall system health status (Workspace Owner/Admin only)",
    responses={200: {'description': 'System health status'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def system_health(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = resolve_workspace(workspaceId)
        if not check_admin_permission(request.user, workspace):
            return Response({'error': 'Workspace Owner/Admin access required'}, status=status.HTTP_403_FORBIDDEN)

        performance_metrics = get_system_performance_metrics()
        services = get_service_health()
        system_status = calculate_system_status(services, performance_metrics)

        oldest_metric = SystemMetric.objects.order_by('timestamp').first()
        if oldest_metric:
            uptime_seconds = (timezone.now() - oldest_metric.timestamp).total_seconds()
            uptime_hours = uptime_seconds / 3600

            uptime = min(99.99, (uptime_hours / (uptime_hours + 0.01)) * 100)
        else:
            uptime = 0

        return Response({
            'system_status': system_status,
            'services': services,
            'performance_metrics': performance_metrics,
            'uptime': uptime
        })

    return await _sync_logic()

@extend_schema(
    tags=["Monitoring"],
    summary="System Metrics",
    description="Get system metrics with filtering (Workspace Owner/Admin only)",
    parameters=[
        {'name': 'MetricType', 'in': 'query', 'schema': {'type': 'string', 'default': 'performance'}, 'description': 'Type of metrics to retrieve'},
        {'name': 'DateFrom', 'in': 'query', 'schema': {'type': 'string', 'format': 'date'}, 'description': 'Start date for metrics'},
        {'name': 'DateTo', 'in': 'query', 'schema': {'type': 'string', 'format': 'date'}, 'description': 'End date for metrics'}
    ],
    responses={200: {'description': 'System metrics data'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def system_metrics(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = resolve_workspace(workspaceId)
        if not check_admin_permission(request.user, workspace):
            return Response({'error': 'Workspace Owner/Admin access required'}, status=status.HTTP_403_FORBIDDEN)

        metric_type = request.GET.get('MetricType', 'performance')
        date_from = request.GET.get('DateFrom')
        date_to = request.GET.get('DateTo')


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

        metrics = SystemMetric.objects.filter(
            metric_type=metric_type,
            timestamp__date__range=[date_from, date_to]
        ).order_by('-timestamp')

        response_time_metrics = SystemMetric.objects.filter(
            metric_name='response_time',
            timestamp__date__range=[date_from, date_to]
        )
        request_metrics = SystemMetric.objects.filter(
            metric_name='total_requests',
            timestamp__date__range=[date_from, date_to]
        )
        error_metrics = SystemMetric.objects.filter(
            metric_name='error_count',
            timestamp__date__range=[date_from, date_to]
        )
        user_metrics = SystemMetric.objects.filter(
            metric_name='concurrent_users',
            timestamp__date__range=[date_from, date_to]
        )

        avg_response_time = response_time_metrics.aggregate(Avg('value'))['value__avg'] or 0
        total_requests = request_metrics.aggregate(Sum('value'))['value__sum'] or 0
        total_errors = error_metrics.aggregate(Sum('value'))['value__sum'] or 0
        peak_concurrent_users = user_metrics.aggregate(Max('value'))['value__max'] or 0

        error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0

        aggregated_data = {
            'avg_response_time': avg_response_time,
            'total_requests': int(total_requests),
            'error_rate': error_rate,
            'peak_concurrent_users': int(peak_concurrent_users)
        }

        alerts = SystemAlert.objects.filter(status='active').order_by('-created_at')

        return Response({
            'metrics': SystemMetricSerializer(metrics, many=True).data,
            'aggregated_data': aggregated_data,
            'alerts': SystemAlertSerializer(alerts, many=True).data
        })

    return await _sync_logic()

@extend_schema(
    tags=["Monitoring"],
    summary="User Usage Details",
    description="Get detailed usage information for user",
    responses={200: {'description': 'Detailed usage data'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def organization_usage_detailed(request, id):
    @sync_to_async
    def _sync_logic():
        if not check_organization_access(request.user, id):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        date_from = request.GET.get('DateFrom')
        date_to = request.GET.get('DateTo')

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

        detailed_usage = get_organization_usage_data(request.user, date_from, date_to)
        usage_trends = get_usage_trends(request.user, date_from, date_to)
        cost_breakdown = get_cost_breakdown(request.user)
        optimization_suggestions = get_optimization_suggestions(request.user)

        return Response({
            'detailed_usage': detailed_usage,
            'usage_trends': usage_trends,
            'cost_breakdown': cost_breakdown,
            'optimization_suggestions': optimization_suggestions
        })
    return await _sync_logic()


@extend_schema(
    tags=["Monitoring"],
    summary="Endpoint Analytics",
    description="Get aggregated metrics of endpoint calls for the workspace sorted by call count (Workspace Owner/Admin only)",
    responses={200: {'description': 'Aggregated endpoint analytics'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def workspace_endpoint_analytics(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = resolve_workspace(workspaceId)
        if not check_admin_permission(request.user, workspace):
            return Response({'error': 'Workspace Owner/Admin access required'}, status=status.HTTP_403_FORBIDDEN)
            
        logs = UserActivityLog.objects.filter(workspace=workspace, activity_type='api_request')
        
        analytics = {}
        import re
        
        for log in logs.iterator():
            endpoint = log.endpoint
            # Normalize UUIDs to standard placeholder
            endpoint = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '{id}', endpoint)
            # Normalize numerical IDs
            endpoint = re.sub(r'/\d+/', '/{id}/', endpoint)
            # Normalize workspace slug in the endpoint path
            if workspace.slug:
                endpoint = endpoint.replace(workspace.slug, '{slug}')
                
            method = log.metadata.get('method', 'GET')
            status_code = log.metadata.get('status_code', 200)
            duration = log.duration_ms or 0
            
            key = f"{method} {endpoint}"
            if key not in analytics:
                analytics[key] = {
                    'method': method,
                    'endpoint': endpoint,
                    'count': 0,
                    'total_duration': 0,
                    'max_duration': 0,
                    'success_count': 0,
                    'last_accessed': log.created_at
                }
                
            entry = analytics[key]
            entry['count'] += 1
            entry['total_duration'] += duration
            if duration > entry['max_duration']:
                entry['max_duration'] = duration
            if isinstance(status_code, int) and 200 <= status_code < 400:
                entry['success_count'] += 1
            if log.created_at > entry['last_accessed']:
                entry['last_accessed'] = log.created_at
                
        results = []
        for key, entry in analytics.items():
            avg_duration = entry['total_duration'] / entry['count'] if entry['count'] > 0 else 0
            success_rate = (entry['success_count'] / entry['count'] * 100) if entry['count'] > 0 else 0
            results.append({
                'method': entry['method'],
                'endpoint': entry['endpoint'],
                'count': entry['count'],
                'avg_duration_ms': round(avg_duration, 2),
                'max_duration_ms': entry['max_duration'],
                'success_rate': round(success_rate, 2),
                'last_accessed': entry['last_accessed']
            })
            
        results.sort(key=lambda x: x['count'], reverse=True)
        
        return Response({
            'workspace_id': str(workspace.id),
            'workspace_name': workspace.name,
            'workspace_slug': workspace.slug,
            'endpoints': results
        })
        
    return await _sync_logic()


def backend_endpoint_analytics(request):
    import re
    import json
    from django.conf import settings
    from django.http import HttpResponseForbidden
    from django.shortcuts import render
    from logs.models import UserActivityLog
    
    # Restrict to superusers or debug mode
    if not settings.DEBUG and not (request.user.is_authenticated and request.user.is_superuser):
        return HttpResponseForbidden("Only superusers are allowed to access endpoint analytics.")
        
    logs = UserActivityLog.objects.filter(activity_type='api_request')
    
    analytics = {}
    detailed_logs = []
    
    for log in logs.iterator():
        endpoint = log.endpoint
        # Normalize UUIDs
        endpoint = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '{id}', endpoint)
        # Normalize numerical IDs
        endpoint = re.sub(r'/\d+/', '/{id}/', endpoint)
        
        method = log.metadata.get('method', 'GET') if log.metadata else 'GET'
        status_code = log.metadata.get('status_code', 200) if log.metadata else 200
        duration = log.duration_ms or 0
        
        key = f"{method} {endpoint}"
        if key not in analytics:
            analytics[key] = {
                'method': method,
                'endpoint': endpoint,
                'count': 0,
                'total_duration': 0,
                'max_duration': 0,
                'min_duration': float('inf'),
                'success_count': 0,
            }
            
        entry = analytics[key]
        entry['count'] += 1
        entry['total_duration'] += duration
        if duration > entry['max_duration']:
            entry['max_duration'] = duration
        if duration < entry['min_duration']:
            entry['min_duration'] = duration
        if isinstance(status_code, int) and 200 <= status_code < 400:
            entry['success_count'] += 1
            
        detailed_logs.append({
            'id': str(log.id),
            'timestamp': log.created_at.isoformat(),
            'user': log.user.email if log.user else 'System/Anonymous',
            'method': method,
            'endpoint': endpoint,
            'raw_endpoint': log.endpoint,
            'duration_ms': duration,
            'status_code': status_code,
            'ip_address': log.ip_address or 'N/A',
            'user_agent': log.metadata.get('user_agent', 'N/A') if log.metadata else 'N/A'
        })
        
    results = []
    for key, entry in analytics.items():
        avg_duration = entry['total_duration'] / entry['count'] if entry['count'] > 0 else 0
        success_rate = (entry['success_count'] / entry['count'] * 100) if entry['count'] > 0 else 0
        results.append({
            'method': entry['method'],
            'endpoint': entry['endpoint'],
            'count': entry['count'],
            'avg_duration_ms': round(avg_duration, 2),
            'max_duration_ms': entry['max_duration'],
            'min_duration_ms': entry['min_duration'] if entry['min_duration'] != float('inf') else 0,
            'success_rate': round(success_rate, 2),
        })
        
    results.sort(key=lambda x: x['count'], reverse=True)
    detailed_logs.sort(key=lambda x: x['timestamp'], reverse=True)
    
    context = {
        'endpoints': results,
        'detailed_logs_json': json.dumps(detailed_logs[:500]),
    }
    return render(request, 'endpoint_analytics.html', context)

