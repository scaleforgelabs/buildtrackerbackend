from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework import status, permissions
from rest_framework.decorators import permission_classes, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Avg, Sum, F
from django.utils import timezone
from django.core.cache import cache
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from datetime import datetime, timedelta
import uuid
import secrets

from .models import Report, ReportTemplate, ScheduledReport, SharedReport
from .serializers import (
    ReportSerializer, ReportGenerateSerializer, PersonalReportGenerateSerializer,
    ReportTemplateSerializer, ScheduledReportSerializer, SharedReportSerializer,
    ReportShareSerializer, ReportDataSerializer, PerformanceSummarySerializer
)
from workspaces.models import Workspace, WorkspaceMember
from tasks.models import Task
from utils import sanitize_input, check_workspace_permission

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'PageSize'
    max_page_size = 100
    page_query_param = 'Page'

def get_filtered_reports(queryset, request):
    report_type = request.GET.get('ReportType')
    status_filter = request.GET.get('Status')
    date_from = request.GET.get('DateFrom')
    date_to = request.GET.get('DateTo')
    
    if report_type:
        queryset = queryset.filter(report_type=report_type)
    
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    
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
    
    return queryset.select_related('workspace', 'created_by').order_by('-created_at')



@extend_schema(
    tags=["Reports"],
    summary="List Workspace Reports",
    description="Get reports for a workspace with filtering",
    responses={200: {'description': 'List of workspace reports'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def workspace_reports(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        reports = workspace.reports.all()
        filtered_reports = get_filtered_reports(reports, request)

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(filtered_reports, request)

        serializer = ReportSerializer(page, many=True)

        return Response({
            'data': serializer.data,
            'pagination': {
                'page': paginator.page.number,
                'page_size': paginator.page_size,
                'total_pages': paginator.page.paginator.num_pages,
                'total_count': paginator.page.paginator.count
            },
            'filters': {
                'report_type': request.GET.get('ReportType', ''),
                'status': request.GET.get('Status', ''),
                'date_from': request.GET.get('DateFrom', ''),
                'date_to': request.GET.get('DateTo', '')
            }
        })

    return await _sync_logic()

@extend_schema(
    tags=["Reports"],
    summary="Generate Workspace Report",
    description="Generate a new report for workspace",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'report_type': {'type': 'string', 'enum': ['task_summary', 'user_performance', 'workspace_overview', 'time_tracking', 'milestone_progress'], 'description': 'Type of report to generate'},
                'parameters': {'type': 'object', 'description': 'Report parameters (date_from, date_to, user_ids, etc.)'},
                'schedule': {'type': 'object', 'properties': {'frequency': {'type': 'string'}, 'recipients': {'type': 'array', 'items': {'type': 'string'}}}, 'description': 'Optional scheduling configuration'}
            },
            'required': ['report_type']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'report_type': {'type': 'string', 'enum': ['task_summary', 'user_performance', 'workspace_overview', 'time_tracking', 'milestone_progress'], 'description': 'Type of report to generate'},
                'parameters': {'type': 'string', 'description': 'Report parameters as JSON string'},
                'schedule': {'type': 'string', 'description': 'Optional scheduling configuration as JSON string'}
            },
            'required': ['report_type']
        }
    },
    responses={201: {'description': 'Report generation started'}}
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def generate_workspace_report(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
            return Response({'error': 'Only workspace owners and admins can generate reports'}, status=status.HTTP_403_FORBIDDEN)

        serializer = ReportGenerateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        job_id = str(uuid.uuid4())


        report = Report.objects.create(
            workspace=workspace,
            report_type=data['report_type'],
            title=f"{dict(Report.REPORT_TYPES)[data['report_type']]} - {timezone.now().strftime('%Y-%m-%d')}",
            parameters=data['parameters'],
            data={},
            job_id=job_id,
            created_by=request.user,
            status='pending'
        )

        from .tasks import generate_workspace_report_task
        generate_workspace_report_task.delay(str(report.id))

        if data.get('schedule'):
            schedule_data = data['schedule']
            ScheduledReport.objects.create(
                workspace=workspace,
                report_type=data['report_type'],
                frequency=schedule_data['frequency'],
                recipients=schedule_data['recipients'],
                parameters=data['parameters'],
                next_run=timezone.now() + timedelta(days=1),
                created_by=request.user
            )

        return Response({
            'report': ReportSerializer(report).data,
            'job_id': job_id,
            'estimated_completion': timezone.now().isoformat(),
            'download_url': f"/api/workspaces/{workspaceId}/reports/{report.id}/export"
        }, status=status.HTTP_201_CREATED)

    return await _sync_logic()

@extend_schema(
    tags=["Reports"],
    summary="Get Report Details",
    description="Get detailed report data",
    responses={200: {'description': 'Report details'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def report_detail(request, workspaceId, id):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        report = get_object_or_404(Report, id=id, workspace=workspace)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        return Response({
            'report': ReportSerializer(report).data,
            'data': report.data,
            'charts': report.data.get('charts', []),
            'summary': {
                'generated_at': report.completed_at,
                'parameters': report.parameters,
                'record_count': len(report.data.get('tasks', [])) if 'tasks' in report.data else 0
            }
        })

    return await _sync_logic()

@extend_schema(
    tags=["Reports"],
    summary="Export Report",
    description="Export report in specified format",
    responses={200: {'description': 'File download'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def export_report(request, workspaceId, id):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        report = get_object_or_404(Report, id=id, workspace=workspace)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        format_type = request.GET.get('Format', 'json').lower()
        include_charts = request.GET.get('IncludeCharts', 'false').lower() == 'true'

        download_url = f"/api/files/reports/{report.id}.{format_type}"
        expires_at = timezone.now() + timedelta(hours=24)

        return Response({
            'download_url': download_url,
            'expires_at': expires_at.isoformat()
        })

    return await _sync_logic()

@extend_schema(
    tags=["Reports"],
    summary="Share Report",
    description="Share report with recipients",
    responses={200: {'description': 'Report shared successfully'}}
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
async def share_report(request, workspaceId, id):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        report = get_object_or_404(Report, id=id, workspace=workspace)

        if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
            return Response({'error': 'Only workspace owners and admins can share reports'}, status=status.HTTP_403_FORBIDDEN)

        serializer = ReportShareSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        share_token = secrets.token_urlsafe(32)

        shared_report = SharedReport.objects.create(
            report=report,
            shared_by=request.user,
            recipients=data['recipients'],
            access_level=data['access_level'],
            message=data.get('message', ''),
            share_token=share_token,
            expires_at=timezone.now() + timedelta(days=30)
        )

        return Response({
            'shared_links': [{
                'share_token': share_token,
                'url': f"/shared/reports/{share_token}",
                'expires_at': shared_report.expires_at.isoformat()
            }],
            'notifications_sent': len(data['recipients'])
        })

    return await _sync_logic()

@extend_schema(
    tags=["Reports"],
    summary="List User Reports in Workspace",
    description="Get personal reports for a user within a workspace (Admin/Owner only)",
    responses={200: {'description': 'List of personal reports'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def user_reports(request, workspaceId, userId):
    @sync_to_async
    def _sync_logic():
        from auth_func.models import CustomUser
        workspace = get_object_or_404(Workspace, id=workspaceId)
        user = get_object_or_404(CustomUser, id=userId)

        if not WorkspaceMember.objects.filter(workspace=workspace, user=user).exists():
            return Response({'error': 'User is not a member of this workspace'}, status=status.HTTP_404_NOT_FOUND)

        if request.user.id != user.id:
            if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        elif not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        reports = Report.objects.filter(user=user, workspace=workspace)
        filtered_reports = get_filtered_reports(reports, request)

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(filtered_reports, request)

        serializer = ReportSerializer(page, many=True)

        tasks = Task.objects.filter(assigned_to=user, workspace=workspace)
        performance_summary = {
            'total_tasks': tasks.count(),
            'completed_tasks': tasks.filter(status='completed').count(),
            'completion_rate': tasks.filter(status='completed').count() / max(tasks.count(), 1) * 100,
        }

        return Response({
            'data': serializer.data,
            'pagination': {
                'page': paginator.page.number,
                'page_size': paginator.page_size,
                'total_pages': paginator.page.paginator.num_pages,
                'total_count': paginator.page.paginator.count
            },
            'performance_summary': performance_summary
        })

    return await _sync_logic()

@extend_schema(
    tags=["Reports"],
    summary="Generate Personal Report",
    description="Generate personal performance report for a user within a workspace (Admin/Owner only)",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'report_type': {'type': 'string', 'enum': ['personal_performance', 'task_history', 'time_summary', 'achievement_report'], 'default': 'personal_performance'},
                'parameters': {'type': 'object', 'description': 'Optional report parameters'}
            }
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'report_type': {'type': 'string', 'enum': ['personal_performance', 'task_history', 'time_summary', 'achievement_report'], 'default': 'personal_performance'},
                'parameters': {'type': 'string', 'description': 'Optional report parameters as JSON string'}
            }
        }
    },
    responses={201: {'description': 'Personal report generated'}}
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def generate_personal_report(request, workspaceId, userId):
    @sync_to_async
    def _sync_logic():
        from auth_func.models import CustomUser
        workspace = get_object_or_404(Workspace, id=workspaceId)
        user = get_object_or_404(CustomUser, id=userId)

        # Check if user is member of workspace
        if not WorkspaceMember.objects.filter(workspace=workspace, user=user).exists():
            return Response({'error': 'User is not a member of this workspace'}, status=status.HTTP_404_NOT_FOUND)

        # Only workspace admin/owner can generate reports for users
        if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        # Default to empty dict if no data provided
        data = request.data if request.data else {}
        serializer = PersonalReportGenerateSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data
        job_id = str(uuid.uuid4())


        report = Report.objects.create(
            workspace=workspace,
            user=user,
            report_type=validated_data['report_type'],
            title=f"{user.email} - {dict(Report.REPORT_TYPES)[validated_data['report_type']]} - {timezone.now().strftime('%Y-%m-%d')}",
            parameters=validated_data.get('parameters', {}),
            data={},
            job_id=job_id,
            created_by=request.user,
            status='pending'
        )

        from .tasks import generate_personal_report_task
        generate_personal_report_task.delay(str(report.id))

        return Response({
            'report': ReportSerializer(report).data,
            'job_id': job_id,
            'download_url': f"/api/workspaces/{workspaceId}/users/{userId}/reports/{report.id}/export"
        }, status=status.HTTP_201_CREATED)

    return await _sync_logic()

@extend_schema(
    tags=["Reports"],
    summary="Get Report Templates",
    description="Get available report templates",
    responses={200: {'description': 'List of report templates'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def report_templates(request):
    @sync_to_async
    def _sync_logic():
        templates = ReportTemplate.objects.filter(is_active=True)
        serializer = ReportTemplateSerializer(templates, many=True)

        categories = templates.values_list('category', flat=True).distinct()

        return Response({
            'templates': serializer.data,
            'categories': list(categories)
        })

    return await _sync_logic()

@extend_schema(
    tags=["Reports"],
    summary="Schedule Report",
    description="Schedule recurring report generation",
    responses={201: {'description': 'Report scheduled successfully'}}
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
async def schedule_report(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
            return Response({'error': 'Only workspace owners and admins can schedule reports'}, status=status.HTTP_403_FORBIDDEN)

        serializer = ScheduledReportSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        scheduled_report = serializer.save(workspace=workspace, created_by=request.user)

        return Response({
            'scheduled_report': ScheduledReportSerializer(scheduled_report).data
        }, status=status.HTTP_201_CREATED)
    return await _sync_logic()

