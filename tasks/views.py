from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework import status, permissions
from rest_framework.decorators import permission_classes, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from datetime import datetime

from .models import Task, TaskComment, TaskCommentAttachment, PersonalTask
from .serializers import (
    TaskSerializer, TaskCreateSerializer, TaskCommentSerializer, 
    TaskAttachmentSerializer, TaskCommentCreateSerializer, PersonalTaskSerializer
)
from .tasks import send_task_assignment_email, send_task_status_update_email
from workspaces.models import Workspace, WorkspaceMember
from utils import sanitize_input, check_workspace_permission, create_workspace_log, create_audit_log, create_user_activity_log, create_notification

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'PageSize'
    max_page_size = 100
    page_query_param = 'Page'

def get_filtered_tasks(queryset, request):
    search_key = request.GET.get('SearchKey')
    status_filter = request.GET.get('Status')
    priority_filter = request.GET.get('Priority')
    milestone_filter = request.GET.get('Milestone')
    sprint_filter = request.GET.get('Sprint')
    date_from = request.GET.get('DateFrom')
    date_to = request.GET.get('DateTo')
    sort_column = request.GET.get('SortColumn', 'created_at')
    sort_order = request.GET.get('SortOrder', 'desc')
    
    if search_key:
        search_key = sanitize_input(search_key)
        from django.contrib.postgres.search import SearchQuery
        
        query = Q(search_vector=SearchQuery(search_key))
        clean_key = search_key.lstrip('#')
        if clean_key.isdigit():
            query |= Q(ticket_number=int(clean_key))
            
        queryset = queryset.filter(query)
    
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    
    if priority_filter:
        queryset = queryset.filter(priority=priority_filter)
    
    if milestone_filter:
        queryset = queryset.filter(milestone=milestone_filter)
    
    if sprint_filter:
        queryset = queryset.filter(sprint=sprint_filter)
    
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
    
    order_prefix = '-' if sort_order == 'desc' else ''
    queryset = queryset.order_by(f"{order_prefix}{sort_column}")
    
    return queryset

@extend_schema(
    tags=["Tasks"],
    summary="Workspace Tasks",
    description="GET: List workspace tasks with filtering. POST: Create new task",
    parameters=[
        {'name': 'Status', 'in': 'query', 'schema': {'type': 'string', 'enum': ['pending', 'in_progress', 'completed']}},
        {'name': 'Priority', 'in': 'query', 'schema': {'type': 'string', 'enum': ['low', 'medium', 'high']}},
        {'name': 'Milestone', 'in': 'query', 'schema': {'type': 'integer'}},
        {'name': 'Sprint', 'in': 'query', 'schema': {'type': 'integer'}},
        {'name': 'DateFrom', 'in': 'query', 'schema': {'type': 'string', 'format': 'date'}},
        {'name': 'DateTo', 'in': 'query', 'schema': {'type': 'string', 'format': 'date'}},
        {'name': 'SearchKey', 'in': 'query', 'schema': {'type': 'string'}},
        {'name': 'Page', 'in': 'query', 'schema': {'type': 'integer', 'default': 1}},
        {'name': 'PageSize', 'in': 'query', 'schema': {'type': 'integer', 'default': 25}},
        {'name': 'SortColumn', 'in': 'query', 'schema': {'type': 'string', 'default': 'created_at'}},
        {'name': 'SortOrder', 'in': 'query', 'schema': {'type': 'string', 'enum': ['asc', 'desc'], 'default': 'desc'}},
    ],
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'task_name': {'type': 'string'},
                'task_description': {'type': 'string'},
                'assigned_to': {'type': 'string'},
                'priority': {'type': 'string', 'enum': ['low', 'medium', 'high']},
                'start_date': {'type': 'string', 'format': 'date'},
                'end_date': {'type': 'string', 'format': 'date'},
                'milestone': {'type': 'integer'},
                'sprint': {'type': 'integer'},
                'percent_complete': {'type': 'integer'},
                'attachments': {'type': 'array', 'items': {'type': 'string'}}
            },
            'required': ['task_name', 'priority']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'task_name': {'type': 'string'},
                'task_description': {'type': 'string'},
                'assigned_to': {'type': 'string'},
                'priority': {'type': 'string', 'enum': ['low', 'medium', 'high']},
                'start_date': {'type': 'string', 'format': 'date'},
                'end_date': {'type': 'string', 'format': 'date'},
                'milestone': {'type': 'integer'},
                'sprint': {'type': 'integer'},
                'percent_complete': {'type': 'integer'},
                'attachments': {'type': 'array', 'items': {'type': 'string', 'format': 'binary'}}
            },
            'required': ['task_name', 'priority']
        }
    },
    responses={
        200: {'description': 'List of tasks'},
        201: {'description': 'Task created'}
    }
)
@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def workspace_tasks(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        try:
            workspace = get_object_or_404(Workspace, id=workspaceId)

            if not check_workspace_permission(request.user, workspace):
                return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

            if request.method == 'GET':
                create_user_activity_log(user=request.user, activity_type='api_request', workspace=workspace, module='tasks', request=request)

                tasks = workspace.tasks.all().select_related(
                    'assigned_to', 'created_by'
                ).prefetch_related(
                    'attachments', 'comments__user', 'comments__attachments'
                )

                if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
                    tasks = tasks.filter(assigned_to=request.user)

                filtered_tasks = get_filtered_tasks(tasks, request)

                paginator = StandardResultsSetPagination()
                page = paginator.paginate_queryset(filtered_tasks, request)

                serializer = TaskSerializer(page, many=True)

                return paginator.get_paginated_response({
                    'data': serializer.data,
                    'pagination': {
                        'page': paginator.page.number,
                        'page_size': paginator.page_size,
                        'total_pages': paginator.page.paginator.num_pages,
                        'total_count': paginator.page.paginator.count
                    },
                    'filters': {
                        'status': request.GET.get('Status', ''),
                        'priority': request.GET.get('Priority', ''),
                        'milestone': request.GET.get('Milestone', ''),
                        'sprint': request.GET.get('Sprint', ''),
                        'search_key': request.GET.get('SearchKey', ''),
                        'sort_column': request.GET.get('SortColumn', 'created_at'),
                        'sort_order': request.GET.get('SortOrder', 'desc')
                    }
                })

            elif request.method == 'POST':
                if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
                    return Response({'error': 'Only owners and admins can create tasks'}, status=status.HTTP_403_FORBIDDEN)

                clean_data = {}
                for key, value in request.data.items():
                    if key != 'attachments' and not hasattr(value, 'read'):
                        clean_data[key] = value

                serializer = TaskCreateSerializer(data=clean_data, context={'workspace': workspace, 'request': request})
                if serializer.is_valid():
                    task = serializer.save()

                    # FAILSAFE: Ensure the status explicitly defaults to what was sent in the payload
                    # (Bypasses potential REST Framework field omission quirks)
                    incoming_status = clean_data.get('status')
                    if incoming_status and incoming_status != task.status:
                        task.status = incoming_status
                        if incoming_status == 'completed':
                            task.percent_complete = 100
                        task.save()

                    create_workspace_log(
                        workspace=workspace,
                        user=request.user,
                        log_type='task_create',
                        action='create',
                        description=f"Created task: {task.task_name}",
                        entity_type='task',
                        entity_id=task.id,
                        metadata={'task_name': task.task_name, 'priority': task.priority, 'status': task.status},
                        request=request
                    )

                    create_audit_log(
                        workspace=workspace,
                        user=request.user,
                        action='create',
                        entity_type='task',
                        entity_id=task.id,
                        new_values={'task_name': task.task_name, 'priority': task.priority, 'status': task.status},
                        request=request
                    )

                    create_user_activity_log(user=request.user, activity_type='api_request', workspace=workspace, module='tasks', request=request)

                    # Task assignment email handled in serializers.py

                    return Response({
                        'task': TaskSerializer(task, context={'request': request}).data,
                        'ticket_number': task.ticket_number
                    }, status=status.HTTP_201_CREATED)

                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            from utils import handle_view_exception
            return handle_view_exception(e, 'tasks.views.workspace_tasks', workspace=workspace if 'workspace' in locals() else None)

    return await _sync_logic()

@extend_schema(
    tags=["Tasks"],
    summary="Task Details",
    description="Get, update, or delete task details (Workspace Member only)",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'task_name': {'type': 'string'},
                'task_description': {'type': 'string'},
                'assigned_to': {'type': 'string'},
                'status': {'type': 'string', 'enum': ['pending', 'in_progress', 'completed']},
                'priority': {'type': 'string', 'enum': ['low', 'medium', 'high']},
                'start_date': {'type': 'string', 'format': 'date'},
                'end_date': {'type': 'string', 'format': 'date'},
                'milestone': {'type': 'integer'},
                'sprint': {'type': 'integer'},
                'percent_complete': {'type': 'integer'},
                'has_blocker': {'type': 'boolean'},
                'blocker_reason': {'type': 'string'},
                'attachments': {'type': 'array', 'items': {'type': 'string'}}
            }
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'task_name': {'type': 'string'},
                'task_description': {'type': 'string'},
                'assigned_to': {'type': 'string'},
                'status': {'type': 'string', 'enum': ['pending', 'in_progress', 'completed']},
                'priority': {'type': 'string', 'enum': ['low', 'medium', 'high']},
                'start_date': {'type': 'string', 'format': 'date'},
                'end_date': {'type': 'string', 'format': 'date'},
                'milestone': {'type': 'integer'},
                'sprint': {'type': 'integer'},
                'percent_complete': {'type': 'integer'},
                'has_blocker': {'type': 'boolean'},
                'blocker_reason': {'type': 'string'},
                'attachments': {'type': 'array', 'items': {'type': 'string', 'format': 'binary'}}
            }
        }
    },
    responses={200: {'description': 'Task details'}}
)
@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def task_detail(request, workspaceId, id):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        task = get_object_or_404(
            Task.objects.select_related('assigned_to', 'created_by').prefetch_related('comments__attachments', 'attachments'),
            id=id, 
            workspace=workspace
        )

        if request.method == 'GET':
            create_user_activity_log(user=request.user, activity_type='api_request', workspace=workspace, module='tasks', request=request)

            serializer = TaskSerializer(task, context={'request': request})
            return Response({
                'task': serializer.data,
                'comments': TaskCommentSerializer(task.comments.all().filter(parent_comment__isnull=True).order_by('created_at'), many=True, context={'request': request}).data,
                'attachments': TaskAttachmentSerializer(task.attachments.all(), many=True, context={'request': request}).data,
                'assigned_user': serializer.data.get('assigned_user'),
                'created_by_user': serializer.data.get('created_by_user')
            })

        elif request.method == 'PUT':
            if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
                return Response({'error': 'Only owners and admins can update tasks'}, status=status.HTTP_403_FORBIDDEN)

            update_data = {}
            for key, value in request.data.items():
                if value is not None and value != '':
                    update_data[key] = value

            serializer = TaskSerializer(task, data=update_data, partial=True)
            if serializer.is_valid():
                old_status = task.status
                old_assigned_to = task.assigned_to
                
                old_values = {}
                for k in update_data.keys():
                    val = getattr(task, k, None)
                    if val is None:
                        old_values[k] = None
                    elif hasattr(val, 'id'):
                        old_values[k] = str(val.id)
                    elif hasattr(val, 'isoformat'):
                        old_values[k] = val.isoformat()
                    else:
                        old_values[k] = str(val)

                serializer.save()

                # Handle new file uploads
                attachment_files = request.FILES.getlist('attachments') if hasattr(request, 'FILES') and request.FILES else []
                if not attachment_files and hasattr(request.data, 'getlist'):
                    attachment_files = [f for f in request.data.getlist('attachments') if hasattr(f, 'read')]
                
                if attachment_files:
                    from utils import validate_file_security
                    from .models import TaskAttachment
                    for attachment_file in attachment_files:
                        is_valid, error = validate_file_security(attachment_file)
                        if not is_valid:
                            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)
                            
                        TaskAttachment.objects.create(
                            task=task,
                            file=attachment_file,
                            file_name=attachment_file.name,
                            uploaded_by=request.user
                        )

                if 'assigned_to' in update_data and old_assigned_to != task.assigned_to:
                    if task.assigned_to:
                        from django.db import transaction
                        transaction.on_commit(lambda x=task.id: send_task_assignment_email.delay(str(x)))

                if 'status' in update_data and old_status != task.status:
                    from django.db import transaction
                    transaction.on_commit(lambda x=task.id, o=old_status, n=task.status: send_task_status_update_email.delay(str(x), o, n))
                    
                    recipients = set()
                    if task.created_by: recipients.add(task.created_by)
                    if task.assigned_to: recipients.add(task.assigned_to)
                    
                    # Notify admins/owners
                    admins = WorkspaceMember.objects.filter(workspace=workspace, role__in=['Owner', 'Admin']).select_related('user')
                    for admin in admins:
                        if admin.user:
                            recipients.add(admin.user)
                    
                    from notifications.models import Notification
                    trigger_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email
                    for recipient in recipients:
                        if recipient:
                            Notification.objects.create(
                                user=recipient,
                                triggered_by=request.user,
                                workspace=workspace,
                                action=f"{trigger_name} updated task status: {task.task_name}",
                                description=f"Status changed from {old_status} to {task.status}",
                                note_type="task_updated",
                                severity="info"
                            )
                    
                other_updated_fields = [k for k in update_data.keys() if k not in ['status', 'assigned_to']]
                if other_updated_fields:
                    updater_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email
                    from django.db import transaction
                    from .tasks import send_task_general_update_email
                    transaction.on_commit(lambda x=task.id, f=other_updated_fields, un=updater_name: send_task_general_update_email.delay(str(x), f, un))
                    
                    recipients = set()
                    if task.created_by: recipients.add(task.created_by)
                    if task.assigned_to: recipients.add(task.assigned_to)
                    
                    # Notify admins/owners
                    admins = WorkspaceMember.objects.filter(workspace=workspace, role__in=['Owner', 'Admin']).select_related('user')
                    for admin in admins:
                        if admin.user:
                            recipients.add(admin.user)
                    
                    from notifications.models import Notification
                    trigger_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email
                    for recipient in recipients:
                        if recipient:
                            Notification.objects.create(
                                user=recipient,
                                triggered_by=request.user,
                                workspace=workspace,
                                action=f"{trigger_name} updated task: {task.task_name}",
                                description=f"Field(s) changed: {', '.join(other_updated_fields)}",
                                note_type="task_updated",
                                severity="info"
                            )

                safe_update_data = {}
                for k, v in update_data.items():
                    if hasattr(v, 'read') or hasattr(v, 'file'):
                        safe_update_data[k] = "[File Upload]"
                    else:
                        safe_update_data[k] = v

                create_workspace_log(
                    workspace=workspace,
                    user=request.user,
                    log_type='task_update',
                    action='update',
                    description=f"Updated task: {task.task_name}",
                    entity_type='task',
                    entity_id=task.id,
                    metadata={'task_name': task.task_name, 'updated_fields': list(update_data.keys())},
                    request=request
                )

                create_audit_log(
                    workspace=workspace,
                    user=request.user,
                    action='update',
                    entity_type='task',
                    entity_id=task.id,
                    old_values=old_values,
                    new_values=safe_update_data,
                    request=request
                )

                if 'status' in update_data and old_status != task.status:
                    create_workspace_log(
                        workspace=workspace,
                        user=request.user,
                        log_type='task_status_change',
                        action='status_change',
                        description=f"Changed task status from {old_status} to {task.status}: {task.task_name}",
                        entity_type='task',
                        entity_id=task.id,
                        metadata={'task_name': task.task_name, 'old_status': old_status, 'new_status': task.status},
                        request=request
                    )

                create_user_activity_log(user=request.user, activity_type='api_request', workspace=workspace, module='tasks', request=request)

                return Response({'task': serializer.data})
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        elif request.method == 'DELETE':
            if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
                return Response({'error': 'Only owners and admins can delete tasks'}, status=status.HTTP_403_FORBIDDEN)

            task_name = task.task_name
            task_id = task.id
            workspace_name = workspace.name
            assignee_id = str(task.assigned_to.id) if task.assigned_to else None
            creator_id = str(task.created_by.id) if task.created_by else None
            deleter_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email
            
            old_values = {'task_name': task.task_name, 'priority': task.priority, 'status': task.status}
            task.delete()
            
            from django.db import transaction
            from .tasks import send_task_deletion_email
            transaction.on_commit(lambda tn=task_name, wn=workspace_name, a=assignee_id, c=creator_id, dn=deleter_name: send_task_deletion_email.delay(tn, wn, a, c, dn))

            create_workspace_log(
                workspace=workspace,
                user=request.user,
                log_type='task_delete',
                action='delete',
                description=f"Deleted task: {task_name}",
                entity_type='task',
                entity_id=task_id,
                metadata={'task_name': task_name},
                request=request
            )

            create_audit_log(
                workspace=workspace,
                user=request.user,
                action='delete',
                entity_type='task',
                entity_id=task_id,
                old_values=old_values,
                request=request
            )

            create_user_activity_log(user=request.user, activity_type='api_request', workspace=workspace, module='tasks', request=request)

            return Response({'message': 'Task deleted successfully'})

    return await _sync_logic()

@extend_schema(
    tags=["Tasks"],
    summary="Update Task Status",
    description="Update task status and completion percentage",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'status': {'type': 'string', 'enum': ['pending', 'in_progress', 'completed']},
                'percent_complete': {'type': 'integer'}
            },
            'required': ['status']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'status': {'type': 'string', 'enum': ['pending', 'in_progress', 'completed']},
                'percent_complete': {'type': 'integer'}
            },
            'required': ['status']
        }
    }
)
@api_view(['PUT'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def update_task_status(request, workspaceId, id):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        task = get_object_or_404(Task, id=id, workspace=workspace)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        status_value = request.data.get('status')
        percent_complete = request.data.get('percent_complete')

        old_status = task.status
        if status_value:
            task.status = status_value
        if percent_complete is not None:
            task.percent_complete = percent_complete

        task.save()

        if status_value and old_status != task.status:
            from django.db import transaction
            transaction.on_commit(lambda x=task.id, o=old_status, n=task.status: send_task_status_update_email.delay(str(x), o, n))

            create_workspace_log(
                workspace=workspace,
                user=request.user,
                log_type='task_status_change',
                action='status_change',
                description=f"Changed task status from {old_status} to {task.status}: {task.task_name}",
                entity_type='task',
                entity_id=task.id,
                metadata={'task_name': task.task_name, 'old_status': old_status, 'new_status': task.status, 'percent_complete': task.percent_complete},
                request=request
            )

            recipients = set()
            if task.created_by: recipients.add(task.created_by)
            if task.assigned_to: recipients.add(task.assigned_to)
            
            # Notify admins/owners
            admins = WorkspaceMember.objects.filter(workspace=workspace, role__in=['Owner', 'Admin']).select_related('user')
            for admin in admins:
                if admin.user:
                    recipients.add(admin.user)
            
            from notifications.models import Notification
            trigger_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email
            for recipient in recipients:
                if recipient:
                    Notification.objects.create(
                        user=recipient,
                        triggered_by=request.user,
                        workspace=workspace,
                        action=f"{trigger_name} updated status: {task.task_name}",
                        description=f"Changed from {old_status} to {task.status}",
                        note_type="task_updated",
                        severity="info"
                    )

        return Response({'task': TaskSerializer(task).data})

    return await _sync_logic()

@extend_schema(
    tags=["Tasks"],
    summary="Assign Task",
    description="Assign task to a user",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'assigned_to': {'type': 'string'}
            },
            'required': ['assigned_to']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'assigned_to': {'type': 'string'}
            },
            'required': ['assigned_to']
        }
    }
)
@api_view(['PUT'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def assign_task(request, workspaceId, id):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        task = get_object_or_404(Task, id=id, workspace=workspace)

        if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
            return Response({'error': 'Only owners and admins can assign tasks'}, status=status.HTTP_403_FORBIDDEN)

        assigned_to = request.data.get('assigned_to')
        if assigned_to:
            task.assigned_to_id = assigned_to
            task.save()

            if task.assigned_to:
                from django.db import transaction
                transaction.on_commit(lambda x=task.id: send_task_assignment_email.delay(str(x)))

                create_workspace_log(
                    workspace=workspace,
                    user=request.user,
                    log_type='task_update',
                    action='assign',
                    description=f"Assigned task {task.task_name} to {task.assigned_to.email}",
                    entity_type='task',
                    entity_id=task.id,
                    metadata={'task_name': task.task_name, 'assigned_to': task.assigned_to.email},
                    request=request
                )

                recipients = set()
                if task.created_by: recipients.add(task.created_by)
                if task.assigned_to: recipients.add(task.assigned_to)
                
                # Notify admins/owners
                admins = WorkspaceMember.objects.filter(workspace=workspace, role__in=['Owner', 'Admin']).select_related('user')
                for admin in admins:
                    if admin.user:
                        recipients.add(admin.user)

                from notifications.models import Notification
                trigger_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email
                for recipient in recipients:
                    if recipient:
                        Notification.objects.create(
                            user=recipient,
                            triggered_by=request.user,
                            workspace=workspace,
                            action=f"{trigger_name} assigned task: {task.task_name}",
                            description=f"Assigned to {task.assigned_to.email}",
                            note_type="task_assigned",
                            severity="info"
                        )

        return Response({'task': TaskSerializer(task).data})

    return await _sync_logic()

@extend_schema(
    tags=["Tasks"],
    summary="Update Task Blocker",
    description="Update task blocker status and reason. Can be updated by assignee or workspace admins/owners",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'has_blocker': {'type': 'boolean'},
                'blocker_reason': {'type': 'string'}
            },
            'required': ['has_blocker']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'has_blocker': {'type': 'boolean'},
                'blocker_reason': {'type': 'string'}
            },
            'required': ['has_blocker']
        }
    }
)
@api_view(['PUT'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def update_task_blocker(request, workspaceId, id):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        task = get_object_or_404(Task, id=id, workspace=workspace)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        is_assignee = task.assigned_to == request.user
        is_admin_or_owner = check_workspace_permission(request.user, workspace, ['Owner', 'Admin'])

        if not (is_assignee or is_admin_or_owner):
            return Response({'error': 'Only task assignee or workspace admins can update blockers'}, status=status.HTTP_403_FORBIDDEN)

        has_blocker = request.data.get('has_blocker')
        blocker_reason = request.data.get('blocker_reason')

        old_has_blocker = task.has_blocker
        old_blocker_reason = task.blocker_reason

        if has_blocker is not None:
            if isinstance(has_blocker, str):
                has_blocker = has_blocker.lower() in ('true', '1', 'yes')
            task.has_blocker = bool(has_blocker)

        if blocker_reason is not None:
            task.blocker_reason = blocker_reason

        task.save()
        
        blocker_activated_or_updated = (
            (task.has_blocker and not old_has_blocker) or 
            (task.has_blocker and blocker_reason is not None and blocker_reason != old_blocker_reason)
        )
        
        if blocker_activated_or_updated:
            recipients = set()
            if task.created_by: recipients.add(task.created_by)
            if task.assigned_to: recipients.add(task.assigned_to)
            
            admins = WorkspaceMember.objects.filter(
                workspace=task.workspace,
                role__in=['Owner', 'Admin']
            ).select_related('user')
            
            for admin in admins:
                if admin.user: recipients.add(admin.user)
                    
            trigger_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email
            from notifications.models import Notification
            trigger_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email
            for recipient in recipients:
                if recipient:
                    Notification.objects.create(
                        user=recipient,
                        triggered_by=request.user,
                        workspace=task.workspace,
                        action=f"{trigger_name} set a blocker on: {task.task_name}",
                        description=f"Reason: {blocker_reason or 'No reason provided'}",
                        note_type='task_blocker',
                        severity='warning'
                    )
            
            create_workspace_log(
                workspace=workspace,
                user=request.user,
                log_type='task_update',
                action='block',
                description=f"Task blocked: {task.task_name}",
                entity_type='task',
                entity_id=task.id,
                metadata={'task_name': task.task_name, 'blocker_reason': blocker_reason},
                request=request
            )
        else:
            # Case where blocker was cleared
            if old_has_blocker and not task.has_blocker:
                recipients = set()
                if task.created_by: recipients.add(task.created_by)
                if task.assigned_to: recipients.add(task.assigned_to)
                
                for admin in admins:
                    if admin.user: recipients.add(admin.user)
                
                trigger_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email
                from notifications.models import Notification
                trigger_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email
                for recipient in recipients:
                    if recipient:
                        Notification.objects.create(
                            user=recipient,
                            triggered_by=request.user,
                            workspace=task.workspace,
                            action=f"{trigger_name} cleared blocker on: {task.task_name}",
                            description=f"Task is no longer blocked",
                            note_type='task_updated',
                            severity='success'
                        )
                
                create_workspace_log(
                    workspace=workspace,
                    user=request.user,
                    log_type='task_update',
                    action='unblock',
                    description=f"Task unblocked: {task.task_name}",
                    entity_type='task',
                    entity_id=task.id,
                    metadata={'task_name': task.task_name},
                    request=request
                )
                
            from .tasks import send_task_blocker_notification
            from django.db import transaction
            transaction.on_commit(lambda x=task.id, b=task.blocker_reason, u=request.user.id: send_task_blocker_notification.delay(str(x), b, str(u)))
            
        return Response({'task': TaskSerializer(task).data})

    return await _sync_logic()

@extend_schema(
    tags=["Tasks"],
    summary="Tasks by Milestone",
    description="Get tasks filtered by milestone"
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def tasks_by_milestone(request, workspaceId, milestone):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        tasks = workspace.tasks.filter(milestone=milestone)

        sprint_filter = request.GET.get('Sprint')
        status_filter = request.GET.get('Status')

        if sprint_filter:
            tasks = tasks.filter(sprint=sprint_filter)
        if status_filter:
            tasks = tasks.filter(status=status_filter)

        serializer = TaskSerializer(tasks, many=True)
        return Response({
            'data': serializer.data,
            'milestone': int(milestone),
            'sprint': int(sprint_filter) if sprint_filter else None
        })

    return await _sync_logic()

@extend_schema(
    tags=["Tasks"],
    summary="Tasks by Sprint",
    description="Get tasks filtered by sprint"
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def tasks_by_sprint(request, workspaceId, sprint):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        tasks = workspace.tasks.filter(sprint=sprint)

        milestone_filter = request.GET.get('Milestone')
        status_filter = request.GET.get('Status')

        if milestone_filter:
            tasks = tasks.filter(milestone=milestone_filter)
        if status_filter:
            tasks = tasks.filter(status=status_filter)

        serializer = TaskSerializer(tasks, many=True)
        return Response({
            'data': serializer.data,
            'sprint': int(sprint),
            'milestone': int(milestone_filter) if milestone_filter else None
        })

    return await _sync_logic()

def get_filtered_comments(queryset, request):
    date_from = request.GET.get('DateFrom')
    sort_column = request.GET.get('SortColumn', 'created_at')
    sort_order = request.GET.get('SortOrder', 'desc')
    
    if date_from:
        try:
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            queryset = queryset.filter(created_at__date__gte=date_from)
        except ValueError:
            pass
    
    order_prefix = '-' if sort_order == 'desc' else ''
    queryset = queryset.order_by(f"{order_prefix}{sort_column}")
    
    return queryset

@extend_schema(
    tags=["Tasks"],
    summary="Task Comments",
    description="GET: List task comments with filtering. POST: Create new comment",
    parameters=[
        {'name': 'DateFrom', 'in': 'query', 'schema': {'type': 'string', 'format': 'date'}},
        {'name': 'SortColumn', 'in': 'query', 'schema': {'type': 'string', 'default': 'created_at'}},
        {'name': 'Page', 'in': 'query', 'schema': {'type': 'integer', 'default': 1}},
        {'name': 'PageSize', 'in': 'query', 'schema': {'type': 'integer', 'default': 20}},
    ],
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'comment_text': {'type': 'string'},
                'parent_comment_id': {'type': 'string'},
                'attachments': {'type': 'array', 'items': {'type': 'string'}}
            },
            'required': ['comment_text']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'comment_text': {'type': 'string'},
                'parent_comment_id': {'type': 'string'},
                'attachments': {'type': 'array', 'items': {'type': 'string', 'format': 'binary'}}
            },
            'required': ['comment_text']
        }
    },
    responses={
        200: {'description': 'List of comments with pagination'},
        201: {'description': 'Comment created'}
    }
)
@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def task_comments(request, workspaceId, taskId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        task = get_object_or_404(Task, id=taskId, workspace=workspace)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'GET':
            comments = task.comments.all().select_related('user').prefetch_related('attachments').order_by('created_at')
            filtered_comments = get_filtered_comments(comments, request)

            paginator = StandardResultsSetPagination()
            paginator.page_size = int(request.GET.get('PageSize', 20))
            page = paginator.paginate_queryset(filtered_comments, request)

            serializer = TaskCommentSerializer(page, many=True, context={'request': request})

            return Response({
                'data': serializer.data,
                'pagination': {
                    'page': paginator.page.number,
                    'page_size': paginator.page_size,
                    'total_pages': paginator.page.paginator.num_pages,
                    'total_count': paginator.page.paginator.count
                }
            })

        elif request.method == 'POST':
            clean_data = {}
            for key, value in request.data.items():
                if key != 'attachments' and not hasattr(value, 'read'):
                    clean_data[key] = value

            serializer = TaskCommentCreateSerializer(data=clean_data, context={'task': task, 'request': request})
            if serializer.is_valid():
                comment = serializer.save()
                
                create_workspace_log(
                    workspace=workspace,
                    user=request.user,
                    log_type='comment_create',
                    action='create',
                    description=f"Added comment on task: {task.task_name}",
                    entity_type='comment',
                    entity_id=comment.id,
                    metadata={'task_name': task.task_name, 'task_id': str(task.id)},
                    request=request
                )

                recipients = set()
                # Notify task creator and assignee
                if task.created_by: recipients.add(task.created_by)
                if task.assigned_to: recipients.add(task.assigned_to)
                
                # Notify admins/owners of the workspace
                from workspaces.models import WorkspaceMember
                admins = WorkspaceMember.objects.filter(workspace=workspace, role__in=['Owner', 'Admin']).select_related('user')
                for admin in admins:
                    if admin.user:
                        recipients.add(admin.user)

                from notifications.models import Notification
                trigger_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email
                for recipient in recipients:
                    if recipient:
                        Notification.objects.create(
                            user=recipient,
                            triggered_by=request.user,
                            workspace=workspace,
                            action=f"{trigger_name} commented on: {task.task_name}",
                            description=f"'{task.task_name}'",
                            note_type="task_comment",
                            severity="info"
                        )

                return Response({
                    'comment': TaskCommentSerializer(comment, context={'request': request}).data
                }, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    return await _sync_logic()

@extend_schema(
    tags=["Tasks"],
    summary="Task Comment Detail",
    description="PUT: Update comment. DELETE: Delete comment",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'comment_text': {'type': 'string'},
                'attachments': {'type': 'array', 'items': {'type': 'string'}}
            },
            'required': ['comment_text']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'comment_text': {'type': 'string'},
                'attachments': {'type': 'array', 'items': {'type': 'string', 'format': 'binary'}}
            },
            'required': ['comment_text']
        }
    },
    responses={
        200: {'description': 'Comment updated'},
        204: {'description': 'Comment deleted'}
    }
)
@api_view(['PUT', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def task_comment_detail(request, workspaceId, taskId, commentId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        task = get_object_or_404(Task, id=taskId, workspace=workspace)
        comment = get_object_or_404(TaskComment, id=commentId, task=task)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'PUT':
            if comment.user != request.user and not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
                return Response({'error': 'Only comment owner or workspace admins can update comments'}, status=status.HTTP_403_FORBIDDEN)

            comment_text = request.data.get('comment_text')
            if comment_text:
                old_text = comment.comment_text
                comment.comment_text = comment_text
                comment.save()

                create_workspace_log(
                    workspace=workspace,
                    user=request.user,
                    log_type='comment_update',
                    action='update',
                    description=f"Updated comment on task: {task.task_name}",
                    entity_type='comment',
                    entity_id=comment.id,
                    metadata={'task_name': task.task_name, 'task_id': str(task.id)},
                    request=request
                )

                create_audit_log(
                    workspace=workspace,
                    user=request.user,
                    action='update',
                    entity_type='comment',
                    entity_id=comment.id,
                    old_values={'comment_text': old_text},
                    new_values={'comment_text': comment_text},
                    request=request
                )

                # Notify relevant users
                recipients = set()
                if task.created_by: recipients.add(task.created_by)
                if task.assigned_to: recipients.add(task.assigned_to)
                
                # Notify admins/owners of the workspace
                admins = WorkspaceMember.objects.filter(workspace=workspace, role__in=['Owner', 'Admin']).select_related('user')
                for admin in admins:
                    if admin.user:
                        recipients.add(admin.user)

                from notifications.models import Notification
                trigger_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email
                for recipient in recipients:
                    if recipient:
                        Notification.objects.create(
                            user=recipient,
                            triggered_by=request.user,
                            workspace=workspace,
                            action=f"{trigger_name} updated a comment: {task.task_name}",
                            description=f"'{task.task_name}'",
                            note_type="task_comment",
                            severity="info"
                        )

            if hasattr(request, 'FILES') and request.FILES:
                attachment_files = request.FILES.getlist('attachments')
                for attachment_file in attachment_files:
                    TaskCommentAttachment.objects.create(
                        comment=comment,
                        file=attachment_file,
                        file_name=attachment_file.name,
                        uploaded_by=request.user
                    )

            return Response({
                'comment': TaskCommentSerializer(comment, context={'request': request}).data
            })

        elif request.method == 'DELETE':
            if comment.user != request.user and not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
                return Response({'error': 'Only comment owner or workspace admins can delete comments'}, status=status.HTTP_403_FORBIDDEN)

            comment_id = comment.id
            old_values = {'comment_text': comment.comment_text, 'task_id': str(task.id)}

            comment_id = comment.id
            comment.delete()

            create_workspace_log(
                workspace=workspace,
                user=request.user,
                log_type='comment_delete',
                action='delete',
                description=f"Deleted comment on task: {task.task_name}",
                entity_type='comment',
                entity_id=comment_id,
                metadata={'task_name': task.task_name, 'task_id': str(task.id)},
                request=request
            )

            create_audit_log(
                workspace=workspace,
                user=request.user,
                action='delete',
                entity_type='comment',
                entity_id=comment_id,
                old_values=old_values,
                request=request
            )

            # Notify relevant users
            recipients = set()
            if task.created_by: recipients.add(task.created_by)
            if task.assigned_to: recipients.add(task.assigned_to)
            
            # Notify admins/owners of the workspace
            admins = WorkspaceMember.objects.filter(workspace=workspace, role__in=['Owner', 'Admin']).select_related('user')
            for admin in admins:
                if admin.user:
                    recipients.add(admin.user)

            from notifications.models import Notification
            trigger_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email
            for recipient in recipients:
                if recipient:
                    Notification.objects.create(
                        user=recipient,
                        workspace=workspace,
                        action=f"{trigger_name} deleted a comment: {task.task_name}",
                        description=f"'{task.task_name}'",
                        note_type="task_comment",
                        severity="info"
                    )

            return Response({'message': 'Comment deleted successfully'})

    return await _sync_logic()

@extend_schema(tags=["Personal Tasks"])
@api_view(['GET', 'POST', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
async def personal_tasks_list(request):
    @sync_to_async
    def _sync_logic():
        if request.method == 'DELETE':
            # clear_all action
            PersonalTask.objects.filter(user=request.user).delete()
            return Response({'message': 'All personal tasks deleted'}, status=status.HTTP_204_NO_CONTENT)
            
        elif request.method == 'POST':
            serializer = PersonalTaskSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(user=request.user)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        else: # GET
            tasks = PersonalTask.objects.filter(user=request.user)
            serializer = PersonalTaskSerializer(tasks, many=True)
            return Response(serializer.data)
            
    return await _sync_logic()

@extend_schema(tags=["Personal Tasks"])
@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
async def personal_task_detail_view(request, pk):
    @sync_to_async
    def _sync_logic():
        try:
            task = PersonalTask.objects.get(pk=pk, user=request.user)
        except PersonalTask.DoesNotExist:
            return Response({'error': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)
            
        if request.method == 'DELETE':
            task.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
            
        elif request.method == 'PUT' or request.method == 'PATCH':
            serializer = PersonalTaskSerializer(task, data=request.data, partial=(request.method == 'PATCH'))
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        else: # GET
            serializer = PersonalTaskSerializer(task)
            return Response(serializer.data)
            
    return await _sync_logic()