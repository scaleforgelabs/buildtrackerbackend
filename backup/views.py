from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework import status, permissions
from rest_framework.decorators import permission_classes, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db.models import Sum
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from datetime import timedelta
from django.http import HttpResponse
import json

from .models import BackupJob, ExportJob
from .serializers import (
    BackupJobSerializer, BackupCreateSerializer, 
    ExportJobSerializer, ExportCreateSerializer
)
from workspaces.models import Workspace, WorkspaceMember
from tasks.models import Task
from wiki.models import WikiDocument
from files.models import File
from utils import check_workspace_permission

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'PageSize'
    max_page_size = 100
    page_query_param = 'Page'

def create_backup_data(workspace, backup_type, include_files):
    """Generate backup data for workspace"""
    backup_data = {
        'workspace': {
            'id': str(workspace.id),
            'name': workspace.name,
            'description': workspace.description,
            'created_at': workspace.created_at.isoformat()
        },
        'members': [],
        'tasks': [],
        'wiki_documents': [],
        'files': []
    }
    
    members = WorkspaceMember.objects.filter(workspace=workspace).select_related('user')
    for member in members:
        backup_data['members'].append({
            'user_email': member.user.email,
            'role': member.role,
            'joined_at': member.joined_at.isoformat()
        })
    
    tasks = Task.objects.filter(workspace=workspace)
    if backup_type == 'incremental':
        tasks = tasks.filter(updated_at__gte=timezone.now() - timedelta(days=7))
    
    for task in tasks:
        backup_data['tasks'].append({
            'id': str(task.id),
            'task_name': task.task_name,
            'task_description': task.task_description,
            'status': task.status,
            'priority': task.priority,
            'assigned_to': task.assigned_to.email if task.assigned_to else None,
            'created_at': task.created_at.isoformat(),
            'updated_at': task.updated_at.isoformat()
        })
    
    wiki_docs = WikiDocument.objects.filter(workspace=workspace)
    if backup_type == 'incremental':
        wiki_docs = wiki_docs.filter(updated_at__gte=timezone.now() - timedelta(days=7))
    
    for doc in wiki_docs:
        backup_data['wiki_documents'].append({
            'id': str(doc.id),
            'document_title': doc.document_title,
            'document_description': doc.document_description,
            'created_at': doc.created_at.isoformat(),
            'updated_at': doc.updated_at.isoformat()
        })
    
    if include_files:
        files = File.objects.filter(workspace=workspace)
        if backup_type == 'incremental':
            files = files.filter(uploaded_at__gte=timezone.now() - timedelta(days=7))
        
        for file_obj in files:
            backup_data['files'].append({
                'id': str(file_obj.id),
                'file_name': file_obj.file_name,
                'file_type': file_obj.file_type,
                'file_size': file_obj.file_size,
                'uploaded_at': file_obj.uploaded_at.isoformat()
            })
    
    return backup_data

def create_export_data(workspace, export_type, format_type, date_range=None):
    """Generate export data based on type and format"""
    export_data = {}
    
    date_filter = {}
    if date_range and 'from' in date_range and 'to' in date_range:
        from datetime import datetime
        date_from = datetime.strptime(date_range['from'], '%Y-%m-%d').date()
        date_to = datetime.strptime(date_range['to'], '%Y-%m-%d').date()
        date_filter = {'created_at__date__range': [date_from, date_to]}
    
    if export_type in ['complete', 'tasks_only']:
        tasks = Task.objects.filter(workspace=workspace, **date_filter)
        export_data['tasks'] = []
        for task in tasks:
            export_data['tasks'].append({
                'id': str(task.id),
                'task_name': task.task_name,
                'task_description': task.task_description,
                'status': task.status,
                'priority': task.priority,
                'assigned_to': task.assigned_to.email if task.assigned_to else None,
                'end_date': task.end_date.isoformat() if task.end_date else None,
                'created_at': task.created_at.isoformat(),
                'updated_at': task.updated_at.isoformat()
            })
    
    if export_type in ['complete', 'wiki_only']:
        wiki_docs = WikiDocument.objects.filter(workspace=workspace, **date_filter)
        export_data['wiki_documents'] = []
        for doc in wiki_docs:
            export_data['wiki_documents'].append({
                'id': str(doc.id),
                'document_title': doc.document_title,
                'document_description': doc.document_description,
                'created_by': doc.author.email,
                'created_at': doc.created_at.isoformat(),
                'updated_at': doc.updated_at.isoformat()
            })
    
    if export_type in ['complete', 'users_only']:
        members = WorkspaceMember.objects.filter(workspace=workspace)
        export_data['members'] = []
        for member in members:
            export_data['members'].append({
                'user_email': member.user.email,
                'role': member.role,
                'joined_at': member.joined_at.isoformat()
            })
    
    return export_data

@extend_schema(
    tags=["Backup"],
    summary="Create Workspace Backup",
    description="Create a backup of workspace data",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'backup_type': {'type': 'string', 'enum': ['full', 'incremental'], 'description': 'Type of backup'},
                'include_files': {'type': 'boolean', 'default': True, 'description': 'Include files in backup'},
                'encryption_enabled': {'type': 'boolean', 'default': False, 'description': 'Enable encryption'}
            },
            'required': ['backup_type']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'backup_type': {'type': 'string', 'enum': ['full', 'incremental'], 'description': 'Type of backup'},
                'include_files': {'type': 'boolean', 'default': True, 'description': 'Include files in backup'},
                'encryption_enabled': {'type': 'boolean', 'default': False, 'description': 'Enable encryption'}
            },
            'required': ['backup_type']
        }
    },
    responses={201: {'description': 'Backup job created'}}
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def create_backup(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Only workspace owners and admins can create backups'}, status=status.HTTP_403_FORBIDDEN)

        serializer = BackupCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        backup_job = BackupJob.objects.create(
            workspace=workspace,
            backup_type=data['backup_type'],
            include_files=data['include_files'],
            encryption_enabled=data['encryption_enabled'],
            created_by=request.user,
            status='processing'
        )

        backup_data = create_backup_data(workspace, data['backup_type'], data['include_files'])

        backup_job.status = 'completed'
        backup_job.completed_at = timezone.now()
        backup_job.file_url = f"/api/backup/download/backup/{backup_job.id}/"
        backup_job.file_size = len(str(backup_data))
        backup_job.save()

        estimated_completion = timezone.now() + timedelta(minutes=5)

        return Response({
            'backup_job': BackupJobSerializer(backup_job).data,
            'download_url': f"/api/backup/download/backup/{backup_job.id}/",
            'estimated_completion': estimated_completion.isoformat()
        }, status=status.HTTP_201_CREATED)

    return await _sync_logic()

@extend_schema(
    tags=["Backup"],
    summary="List Workspace Backups",
    description="Get list of workspace backups",
    responses={200: {'description': 'List of backups'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def list_backups(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        backups = workspace.backup_jobs.all()

        backup_type = request.GET.get('BackupType')
        if backup_type:
            backups = backups.filter(backup_type=backup_type)

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(backups, request)

        serializer = BackupJobSerializer(page, many=True)

        storage_used = backups.aggregate(total=Sum('file_size'))['total'] or 0

        return Response({
            'data': serializer.data,
            'pagination': {
                'page': paginator.page.number,
                'page_size': paginator.page_size,
                'total_pages': paginator.page.paginator.num_pages,
                'total_count': paginator.page.paginator.count
            },
            'storage_used': storage_used
        })

    return await _sync_logic()

@extend_schema(
    tags=["Backup"],
    summary="Create Data Export",
    description="Create an export of workspace data",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'export_type': {'type': 'string', 'enum': ['complete', 'tasks_only', 'wiki_only', 'users_only'], 'description': 'Type of export'},
                'format': {'type': 'string', 'enum': ['json', 'csv', 'excel'], 'description': 'Export format'},
                'date_range': {'type': 'object', 'properties': {'from': {'type': 'string', 'format': 'date'}, 'to': {'type': 'string', 'format': 'date'}}, 'description': 'Date range filter'}
            },
            'required': ['export_type', 'format']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'export_type': {'type': 'string', 'enum': ['complete', 'tasks_only', 'wiki_only', 'users_only'], 'description': 'Type of export'},
                'format': {'type': 'string', 'enum': ['json', 'csv', 'excel'], 'description': 'Export format'},
                'date_range': {'type': 'string', 'description': 'Date range filter as JSON string'}
            },
            'required': ['export_type', 'format']
        }
    },
    responses={201: {'description': 'Export job created'}}
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def create_export(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Only workspace owners and admins can create exports'}, status=status.HTTP_403_FORBIDDEN)

        serializer = ExportCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        export_job = ExportJob.objects.create(
            workspace=workspace,
            export_type=data['export_type'],
            format=data['format'],
            date_range=data.get('date_range', {}),
            created_by=request.user,
            status='processing'
        )

        export_data = create_export_data(
            workspace, 
            data['export_type'], 
            data['format'], 
            data.get('date_range')
        )

        export_job.status = 'completed'
        export_job.completed_at = timezone.now()
        export_job.file_url = f"/api/backup/download/export/{export_job.id}/"
        export_job.file_size = len(str(export_data))
        export_job.save()

        estimated_completion = timezone.now() + timedelta(minutes=2)

        return Response({
            'export_job': ExportJobSerializer(export_job).data,
            'download_url': export_job.file_url,
            'estimated_completion': estimated_completion.isoformat()
        }, status=status.HTTP_201_CREATED)




    return await _sync_logic()

@extend_schema(
    tags=["Backup"],
    summary="Download Backup File",
    description="Download a backup file",
    responses={200: {'description': 'Backup file'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def download_backup(request, backup_id):
    @sync_to_async
    def _sync_logic():
        backup_job = get_object_or_404(BackupJob, id=backup_id)

        if not check_workspace_permission(request.user, backup_job.workspace):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        if backup_job.status != 'completed':
            return Response({'error': 'Backup not completed yet'}, status=status.HTTP_400_BAD_REQUEST)

        backup_data = create_backup_data(
            backup_job.workspace, 
            backup_job.backup_type, 
            backup_job.include_files
        )

        response = HttpResponse(json.dumps(backup_data, indent=2), content_type='application/json')
        response['Content-Disposition'] = f'attachment; filename="backup_{backup_job.workspace.name}_{backup_job.id}.json"'

        return response

    return await _sync_logic()

@extend_schema(
    tags=["Backup"],
    summary="Download Export File",
    description="Download an export file",
    responses={200: {'description': 'Export file'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def download_export(request, export_id):
    @sync_to_async
    def _sync_logic():
        export_job = get_object_or_404(ExportJob, id=export_id)

        if not check_workspace_permission(request.user, export_job.workspace):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        if export_job.status != 'completed':
            return Response({'error': 'Export not completed yet'}, status=status.HTTP_400_BAD_REQUEST)

        export_data = create_export_data(
            export_job.workspace,
            export_job.export_type,
            export_job.format,
            export_job.date_range
        )

        if export_job.format == 'json':
            response = HttpResponse(json.dumps(export_data, indent=2), content_type='application/json')
            filename = f"export_{export_job.workspace.name}_{export_job.id}.json"
        elif export_job.format == 'csv':
            response = HttpResponse(str(export_data), content_type='text/csv')
            filename = f"export_{export_job.workspace.name}_{export_job.id}.csv"
        else:
            response = HttpResponse(str(export_data), content_type='application/vnd.ms-excel')
            filename = f"export_{export_job.workspace.name}_{export_job.id}.xlsx"

        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response


    return await _sync_logic()

@extend_schema(
    tags=["Backup"],
    summary="List Workspace Exports",
    description="Get list of workspace exports",
    responses={200: {'description': 'List of exports'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def list_exports(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        exports = workspace.export_jobs.all()

        export_type = request.GET.get('ExportType')
        if export_type:
            exports = exports.filter(export_type=export_type)

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(exports, request)

        serializer = ExportJobSerializer(page, many=True)

        storage_used = exports.aggregate(total=Sum('file_size'))['total'] or 0

        return Response({
            'data': serializer.data,
            'pagination': {
                'page': paginator.page.number,
                'page_size': paginator.page_size,
                'total_pages': paginator.page.paginator.num_pages,
                'total_count': paginator.page.paginator.count
            },
            'storage_used': storage_used
        })
    return await _sync_logic()

