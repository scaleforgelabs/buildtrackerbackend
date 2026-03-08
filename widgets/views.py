from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework import status, permissions
from rest_framework.decorators import permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Count, Avg
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from datetime import datetime, timedelta

from .models import DashboardWidget, WidgetLayout
from .serializers import (
    DashboardWidgetSerializer, WidgetLayoutSerializer, 
    UserDashboardSerializer, UpdateDashboardSerializer, WidgetDataSerializer
)
from auth_func.models import CustomUser
from workspaces.models import Workspace, WorkspaceMember
from tasks.models import Task
from utils import check_workspace_permission


AVAILABLE_WIDGETS = [
    {
        'widget_type': 'task_summary',
        'name': 'Task Summary',
        'description': 'Overview of all tasks with counts by status',
        'default_width': 4,
        'default_height': 3,
        'category': 'tasks'
    },
    {
        'widget_type': 'recent_tasks',
        'name': 'Recent Tasks',
        'description': 'List of recently created or updated tasks',
        'default_width': 6,
        'default_height': 4,
        'category': 'tasks'
    },
    {
        'widget_type': 'team_performance',
        'name': 'Team Performance',
        'description': 'Team member performance metrics',
        'default_width': 6,
        'default_height': 4,
        'category': 'analytics'
    },
    {
        'widget_type': 'milestone_progress',
        'name': 'Milestone Progress',
        'description': 'Progress tracking for milestones',
        'default_width': 4,
        'default_height': 3,
        'category': 'progress'
    },
    {
        'widget_type': 'sprint_burndown',
        'name': 'Sprint Burndown',
        'description': 'Sprint burndown chart',
        'default_width': 6,
        'default_height': 4,
        'category': 'sprints'
    },
    {
        'widget_type': 'priority_distribution',
        'name': 'Priority Distribution',
        'description': 'Task distribution by priority',
        'default_width': 4,
        'default_height': 3,
        'category': 'analytics'
    },
    {
        'widget_type': 'status_chart',
        'name': 'Status Chart',
        'description': 'Visual breakdown of task statuses',
        'default_width': 4,
        'default_height': 3,
        'category': 'analytics'
    },
    {
        'widget_type': 'overdue_tasks',
        'name': 'Overdue Tasks',
        'description': 'List of overdue tasks',
        'default_width': 4,
        'default_height': 4,
        'category': 'tasks'
    },
    {
        'widget_type': 'completion_trend',
        'name': 'Completion Trend',
        'description': 'Task completion trend over time',
        'default_width': 6,
        'default_height': 4,
        'category': 'analytics'
    },
    {
        'widget_type': 'velocity_chart',
        'name': 'Velocity Chart',
        'description': 'Team velocity over sprints',
        'default_width': 6,
        'default_height': 4,
        'category': 'sprints'
    }
]


def get_widget_data(widget_type, workspace, date_from=None, date_to=None):
    tasks = Task.objects.filter(workspace=workspace)
    if date_from:
        tasks = tasks.filter(created_at__gte=date_from)
    if date_to:
        tasks = tasks.filter(created_at__lte=date_to)
    
    if widget_type == 'task_summary':
        return {
            'total': tasks.count(),
            'completed': tasks.filter(status='completed').count(),
            'in_progress': tasks.filter(status='in_progress').count(),
            'pending': tasks.filter(status='pending').count(),
            'blocked': tasks.filter(status='blocked').count()
        }
    
    elif widget_type == 'recent_tasks':
        recent = tasks.order_by('-created_at')[:10]
        return [{
            'id': str(task.id),
            'title': task.task_name,
            'status': task.status,
            'priority': task.priority,
            'created_at': task.created_at.isoformat()
        } for task in recent]
    
    elif widget_type == 'team_performance':
        members = WorkspaceMember.objects.filter(workspace=workspace).select_related('user')
        performance = []
        for member in members:
            member_tasks = tasks.filter(assigned_to=member.user)
            completed = member_tasks.filter(status='completed').count()
            performance.append({
                'member': member.user.email,
                'total_tasks': member_tasks.count(),
                'completed': completed,
                'completion_rate': (completed / max(member_tasks.count(), 1)) * 100
            })
        return performance
    
    elif widget_type == 'milestone_progress':
        milestones = tasks.values('milestone').distinct()
        progress = []
        for m in milestones:
            if m['milestone']:
                m_tasks = tasks.filter(milestone=m['milestone'])
                completed = m_tasks.filter(status='completed').count()
                progress.append({
                    'milestone': m['milestone'],
                    'total': m_tasks.count(),
                    'completed': completed,
                    'progress': (completed / max(m_tasks.count(), 1)) * 100
                })
        return progress
    
    elif widget_type == 'sprint_burndown':
        sprints = tasks.values('sprint').distinct()
        burndown = []
        for s in sprints:
            if s['sprint']:
                s_tasks = tasks.filter(sprint=s['sprint'])
                completed = s_tasks.filter(status='completed').count()
                burndown.append({
                    'sprint': s['sprint'],
                    'total': s_tasks.count(),
                    'completed': completed,
                    'remaining': s_tasks.count() - completed
                })
        return burndown
    
    elif widget_type == 'priority_distribution':
        priorities = tasks.values('priority').annotate(count=Count('id'))
        return [{'priority': p['priority'], 'count': p['count']} for p in priorities]
    
    elif widget_type == 'status_chart':
        statuses = tasks.values('status').annotate(count=Count('id'))
        return [{'status': s['status'], 'count': s['count']} for s in statuses]
    
    elif widget_type == 'overdue_tasks':
        overdue = tasks.filter(
            end_date__lt=timezone.now().date(),
            status__in=['pending', 'in_progress']
        ).order_by('end_date')[:10]
        return [{
            'id': str(task.id),
            'title': task.task_name,
            'end_date': task.end_date.isoformat(),
            'days_overdue': (timezone.now().date() - task.end_date).days
        } for task in overdue]
    
    elif widget_type == 'completion_trend':
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=30)
        trend = []
        current = start_date
        while current <= end_date:
            completed = tasks.filter(
                status='completed',
                updated_at__date=current
            ).count()
            trend.append({
                'date': current.isoformat(),
                'completed': completed
            })
            current += timedelta(days=1)
        return trend
    
    elif widget_type == 'velocity_chart':
        sprints = tasks.values('sprint').distinct()
        velocity = []
        for s in sprints:
            if s['sprint']:
                completed = tasks.filter(
                    sprint=s['sprint'],
                    status='completed'
                ).count()
                velocity.append({
                    'sprint': s['sprint'],
                    'velocity': completed
                })
        return velocity
    
    return {}


@extend_schema(
    tags=["Dashboard Widgets"],
    summary="Get/Update User Dashboard Widgets",
    description="Get or update widgets and layout for user dashboard"
)
@api_view(['GET', 'PUT'])
@permission_classes([permissions.IsAuthenticated])
async def get_user_dashboard_widgets(request, userId):
    @sync_to_async
    def _sync_logic():
        user = get_object_or_404(CustomUser, id=userId)

        if request.user.id != user.id:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'GET':
            widgets = DashboardWidget.objects.filter(user=user)
            layout, _ = WidgetLayout.objects.get_or_create(user=user)

            response_data = {
                'widgets': DashboardWidgetSerializer(widgets, many=True).data,
                'layout': WidgetLayoutSerializer(layout).data,
                'available_widgets': AVAILABLE_WIDGETS
            }

            return Response(response_data)

        elif request.method == 'PUT':
            widgets_data = request.data.get('widgets', [])
            layout_data = request.data.get('layout', {})

            # Update or create widgets
            DashboardWidget.objects.filter(user=user).delete()
            widgets = []
            for widget_data in widgets_data:
                widget = DashboardWidget.objects.create(
                    user=user,
                    widget_type=widget_data['widget_type'],
                    title=widget_data['title'],
                    position_x=widget_data.get('position_x', 0),
                    position_y=widget_data.get('position_y', 0),
                    width=widget_data.get('width', 4),
                    height=widget_data.get('height', 4),
                    is_visible=widget_data.get('is_visible', True),
                    config=widget_data.get('config', {})
                )
                widgets.append(widget)

            # Update layout
            layout, _ = WidgetLayout.objects.get_or_create(user=user)
            layout.layout_config = layout_data.get('layout_config', {})
            layout.columns = layout_data.get('columns', 12)
            layout.save()

            response_data = {
                'widgets': DashboardWidgetSerializer(widgets, many=True).data,
                'layout': WidgetLayoutSerializer(layout).data
            }

            return Response(response_data)


    return await _sync_logic()

@extend_schema(
    tags=["Dashboard Widgets"],
    summary="Get Widget Data",
    description="Get data for specific widget type in workspace",
    parameters=[
        OpenApiParameter(
            name='widgetType',
            type=str,
            location=OpenApiParameter.PATH,
            description='Widget type to fetch data for',
            enum=[
                'task_summary',
                'recent_tasks',
                'team_performance',
                'milestone_progress',
                'sprint_burndown',
                'priority_distribution',
                'status_chart',
                'overdue_tasks',
                'completion_trend',
                'velocity_chart'
            ],
            required=True
        ),
        OpenApiParameter(
            name='DateFrom',
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            description='Filter data from this date (YYYY-MM-DD)',
            required=False
        ),
        OpenApiParameter(
            name='DateTo',
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            description='Filter data until this date (YYYY-MM-DD)',
            required=False
        )
    ]
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def get_workspace_widget_data(request, workspaceId, widgetType):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

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

        widget_data = get_widget_data(widgetType, workspace, date_from, date_to)

        response_data = {
            'widget_data': widget_data,
            'last_updated': timezone.now().isoformat(),
            'refresh_interval': 300  # 5 minutes
        }

        return Response(response_data)
    return await _sync_logic()

