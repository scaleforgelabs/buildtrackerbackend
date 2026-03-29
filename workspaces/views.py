from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework import status, permissions
from rest_framework.decorators import permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta
from drf_spectacular.utils import extend_schema
import secrets
import string
from .models import Workspace, WorkspaceMember, WorkspaceInvitation, WorkspaceSettings
from .serializers import (
    WorkspaceSerializer, WorkspaceCreateSerializer, WorkspaceMemberSerializer,
    WorkspaceInvitationSerializer, WorkspaceMemberCreateSerializer
)
from utils import sanitize_input, check_workspace_permission, create_workspace_log, create_audit_log, create_user_activity_log, create_notification

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'PageSize'
    max_page_size = 100
    page_query_param = 'Page'

def get_filtered_queryset(queryset, request):
    search_key = request.GET.get('SearchKey')
    date_from = request.GET.get('DateFrom')
    date_to = request.GET.get('DateTo')
    sort_column = request.GET.get('SortColumn', 'joined_at')
    sort_order = request.GET.get('SortOrder', 'desc')
    status_filter = request.GET.get('Status')
    
    if search_key:
        search_key = sanitize_input(search_key)
        queryset = queryset.filter(
            Q(name__icontains=search_key) | 
            Q(job_role__icontains=search_key) |
            Q(email__icontains=search_key)
        )
    
    if date_from:
        queryset = queryset.filter(joined_at__gte=date_from)
    
    if date_to:
        queryset = queryset.filter(joined_at__lte=date_to)
    
    if status_filter:
        queryset = queryset.filter(user_status=status_filter)
    
    order_prefix = '-' if sort_order == 'desc' else ''
    queryset = queryset.order_by(f"{order_prefix}{sort_column}")
    
    return queryset

def get_filtered_workspaces(queryset, request):
    search_key = request.GET.get('SearchKey')
    date_from = request.GET.get('DateFrom')
    date_to = request.GET.get('DateTo')
    sort_column = request.GET.get('SortColumn', 'created_at')
    sort_order = request.GET.get('SortOrder', 'desc')
    status_filter = request.GET.get('Status')
    
    if search_key:
        search_key = sanitize_input(search_key)
        queryset = queryset.filter(
            Q(name__icontains=search_key) | 
            Q(description__icontains=search_key) |
            Q(type__icontains=search_key)
        )
    
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)
    
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    
    order_prefix = '-' if sort_order == 'desc' else ''
    queryset = queryset.order_by(f"{order_prefix}{sort_column}")
    
    return queryset

@extend_schema(
    tags=["Workspaces"],
    summary="List/Create Workspaces",
    description="GET: List user workspaces with pagination and filtering. POST: Create new workspace",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string', 'description': 'Workspace name'},
                'description': {'type': 'string', 'description': 'Workspace description'},
                'type': {'type': 'string', 'enum': ['Construction', 'Software', 'Event', 'Other'], 'description': 'Workspace type'}
            },
            'required': ['name']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string', 'description': 'Workspace name'},
                'description': {'type': 'string', 'description': 'Workspace description'},
                'type': {'type': 'string', 'enum': ['Construction', 'Software', 'Event', 'Other'], 'description': 'Workspace type'}
            },
            'required': ['name']
        }
    },
    responses={
        200: {
            'description': 'List of workspaces',
            'type': 'object',
            'properties': {
                'data': {'type': 'array'},
                'pagination': {'type': 'object'}
            }
        },
        201: {
            'description': 'Workspace created',
            'type': 'object',
            'properties': {
                'workspace': {'type': 'object'}
            }
        },
        400: {'description': 'Invalid input'},
        402: {'description': 'Workspace limit exceeded'},
        403: {'description': 'Permission denied'}
    }
)
@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
async def workspaces_list_create(request):
    @sync_to_async
    def _sync_logic():
        if request.method == 'GET':
            create_user_activity_log(user=request.user, activity_type='api_request', module='workspaces', request=request)

            user_workspaces = Workspace.objects.filter(
                members__user=request.user
            ).distinct().select_related('owner').prefetch_related('members').annotate(
                member_count=Count('members')
            )

            filtered_workspaces = get_filtered_workspaces(user_workspaces, request)

            paginator = StandardResultsSetPagination()
            page = paginator.paginate_queryset(filtered_workspaces, request)

            serializer = WorkspaceSerializer(page, many=True, context={'request': request})

            return paginator.get_paginated_response({
                'data': serializer.data,
                'pagination': {
                    'page': paginator.page.number,
                    'page_size': paginator.page_size,
                    'total_pages': paginator.page.paginator.num_pages,
                    'total_count': paginator.page.paginator.count
                },
                'filters': {
                    'search_key': request.GET.get('SearchKey', ''),
                    'sort_column': request.GET.get('SortColumn', 'created_at'),
                    'sort_order': request.GET.get('SortOrder', 'desc')
                }
            })

        elif request.method == 'POST':

            from organizations.user_org_views import calculate_user_stats, get_plan_limits
            current_usage = calculate_user_stats(request.user)
            limits = get_plan_limits(request.user.plan_type)

            if current_usage['workspace_count'] >= limits['max_workspaces']:
                return Response(
                    {'error': f"Workspace limit reached. You have {current_usage['workspace_count']} workspaces (Limit: {limits['max_workspaces']}). Please upgrade your plan to create more workspaces."}, 
                    status=status.HTTP_402_PAYMENT_REQUIRED
                )

            serializer = WorkspaceCreateSerializer(data=request.data, context={'request': request})
            if serializer.is_valid():
                workspace = serializer.save()

                create_user_activity_log(user=request.user, activity_type='api_request', workspace=workspace, module='workspaces', request=request)


                from .tasks import send_workspace_creation_email
                from django.db import transaction
                transaction.on_commit(lambda x=workspace.id: send_workspace_creation_email.delay(str(x)))

                return Response(
                    {'workspace': WorkspaceSerializer(workspace, context={'request': request}).data},
                    status=status.HTTP_201_CREATED
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    return await _sync_logic()

@extend_schema(
    tags=["Workspaces"],
    summary="Workspace Detail",
    description="GET: Get workspace details. PUT: Update workspace. DELETE: Delete workspace",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string', 'description': 'Workspace name'},
                'description': {'type': 'string', 'description': 'Workspace description'},
                'type': {'type': 'string', 'enum': ['Construction', 'Software', 'Event', 'Other'], 'description': 'Workspace type'}
            }
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string', 'description': 'Workspace name'},
                'description': {'type': 'string', 'description': 'Workspace description'},
                'type': {'type': 'string', 'enum': ['Construction', 'Software', 'Event', 'Other'], 'description': 'Workspace type'}
            }
        }
    },
    responses={
        200: {
            'type': 'object',
            'properties': {
                'workspace': {'type': 'object'},
                'members': {'type': 'array'},
                'member_count': {'type': 'integer'},
                'user_role': {'type': 'string'},
                'no_of_tickets': {'type': 'integer'}
            }
        },
        400: {'description': 'Invalid input'},
        403: {'description': 'Permission denied'},
        404: {'description': 'Workspace not found'}
    }
)
@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
async def workspace_detail(request, id):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace.objects.prefetch_related('members'), id=id)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        # Block write operations on archived workspaces
        if request.method in ['PUT', 'DELETE'] and workspace.status == 'archived':
            return Response({'error': 'Cannot modify archived workspace'}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'GET':
            create_user_activity_log(user=request.user, activity_type='api_request', workspace=workspace, module='workspaces', request=request)

            members = workspace.members.all()
            member_count = members.count()

            try:
                user_member = members.get(user=request.user)
                user_role = user_member.role
            except WorkspaceMember.DoesNotExist:
                user_role = None

            workspace_data = WorkspaceSerializer(workspace, context={'request': request}).data
            members_data = WorkspaceMemberSerializer(members, many=True).data

            return Response({
                'workspace': workspace_data,
                'members': members_data,
                'member_count': member_count,
                'user_role': user_role,
                'no_of_tickets': workspace.no_of_tickets
            })

        elif request.method == 'PUT':
            if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
                return Response({'error': 'Only owners and admins can update workspace'}, status=status.HTTP_403_FORBIDDEN)

            serializer = WorkspaceSerializer(workspace, data=request.data, partial=True, context={'request': request})
            if serializer.is_valid():
                old_values = {k: getattr(workspace, k, None) for k in request.data.keys()}
                serializer.save()

                create_workspace_log(
                    workspace=workspace,
                    user=request.user,
                    log_type='workspace_update',
                    action='update',
                    description=f"Updated workspace: {workspace.name}",
                    entity_type='workspace',
                    entity_id=workspace.id,
                    metadata={'workspace_name': workspace.name, 'updated_fields': list(request.data.keys())},
                    request=request
                )

                create_audit_log(
                    workspace=workspace,
                    user=request.user,
                    action='update',
                    entity_type='workspace',
                    entity_id=workspace.id,
                    old_values=old_values,
                    new_values=request.data,
                    request=request
                )

                create_user_activity_log(user=request.user, activity_type='api_request', workspace=workspace, module='workspaces', request=request)

                return Response({'workspace': serializer.data})
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        elif request.method == 'DELETE':
            if not check_workspace_permission(request.user, workspace, ['Owner']):
                return Response({'error': 'Only workspace owner can delete workspace'}, status=status.HTTP_403_FORBIDDEN)

            workspace.delete()
            return Response({'message': 'Workspace deleted successfully'})

    return await _sync_logic()

@extend_schema(
    tags=["Workspaces"],
    summary="Workspace Members",
    description="GET: List workspace members. POST: Add new member to workspace",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'user_id': {'type': 'integer', 'description': 'User ID to add'},
                'role': {'type': 'string', 'description': 'Member role'},
                'phone': {'type': 'string', 'description': 'Phone number'},
                'job_role': {'type': 'string', 'description': 'Job role'}
            },
            'required': ['user_id', 'role']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'user_id': {'type': 'integer', 'description': 'User ID to add'},
                'role': {'type': 'string', 'description': 'Member role'},
                'phone': {'type': 'string', 'description': 'Phone number'},
                'job_role': {'type': 'string', 'description': 'Job role'}
            },
            'required': ['user_id', 'role']
        }
    },
    responses={
        200: {
            'description': 'List of members',
            'type': 'object',
            'properties': {
                'data': {'type': 'array'},
                'pagination': {'type': 'object'}
            }
        },
        201: {
            'description': 'Member added',
            'type': 'object',
            'properties': {
                'member': {'type': 'object'}
            }
        },
        400: {'description': 'Invalid input'},
        402: {'description': 'User limit exceeded'},
        403: {'description': 'Permission denied'}
    }
)
@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
async def workspace_members(request, id):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=id)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'GET':
            members = workspace.members.all().select_related('user')
            filtered_members = get_filtered_queryset(members, request)

            paginator = StandardResultsSetPagination()
            page = paginator.paginate_queryset(filtered_members, request)

            serializer = WorkspaceMemberSerializer(page, many=True)

            return paginator.get_paginated_response({
                'data': serializer.data,
                'pagination': {
                    'page': paginator.page.number,
                    'page_size': paginator.page_size,
                    'total_pages': paginator.page.paginator.num_pages,
                    'total_count': paginator.page.paginator.count
                }
            })

        elif request.method == 'POST':
            if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
                return Response({'error': 'Only owners and admins can add members'}, status=status.HTTP_403_FORBIDDEN)

            from organizations.user_org_views import calculate_user_stats, get_plan_limits
            current_usage = calculate_user_stats(workspace.owner)
            limits = get_plan_limits(workspace.owner.plan_type)

            if current_usage['user_count'] >= limits['max_users']:
                return Response(
                    {'error': 'User limit exceeded for workspace owner plan'}, 
                    status=status.HTTP_402_PAYMENT_REQUIRED
                )

            serializer = WorkspaceMemberCreateSerializer(data=request.data, context={'workspace': workspace})
            if serializer.is_valid():
                member = serializer.save()

                create_workspace_log(
                    workspace=workspace,
                    user=request.user,
                    log_type='team_update',
                    action='member_add',
                    description=f"Added member {member.user.email} to workspace",
                    entity_type='member',
                    entity_id=member.id,
                    metadata={'member_email': member.user.email, 'role': member.role},
                    request=request
                )

                create_audit_log(
                    workspace=workspace,
                    user=request.user,
                    action='create',
                    entity_type='member',
                    entity_id=member.id,
                    new_values={'user_email': member.user.email, 'role': member.role},
                    request=request
                )

                create_notification(
                    user=member.user,
                    workspace=workspace,
                    action=f"Added to Workspace: {workspace.name}",
                    description=f"You have been added to {workspace.name} as {member.role}",
                    note_type="workspace_access",
                    severity="success",
                    triggered_by=request.user
                )

                create_user_activity_log(user=request.user, activity_type='api_request', workspace=workspace, module='workspaces', request=request)

                return Response(
                    {'member': WorkspaceMemberSerializer(member).data},
                    status=status.HTTP_201_CREATED
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    return await _sync_logic()

@extend_schema(
    tags=["Workspaces"],
    summary="Workspace Member Detail",
    description="PUT: Update member role. DELETE: Remove member from workspace",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'role': {'type': 'string', 'enum': ['Owner', 'Admin', 'Member'], 'description': 'Member role'},
                'name': {'type': 'string', 'description': 'Member name'},
                'phone': {'type': 'string', 'description': 'Phone number'},
                'job_role': {'type': 'string', 'description': 'Job role'},
                'user_status': {'type': 'string', 'enum': ['active', 'busy', 'offline'], 'description': 'Member status'}
            }
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'role': {'type': 'string', 'enum': ['Owner', 'Admin', 'Member'], 'description': 'Member role'},
                'name': {'type': 'string', 'description': 'Member name'},
                'phone': {'type': 'string', 'description': 'Phone number'},
                'job_role': {'type': 'string', 'description': 'Job role'},
                'user_status': {'type': 'string', 'enum': ['active', 'busy', 'offline'], 'description': 'Member status'}
            }
        }
    },
    responses={
        200: {
            'type': 'object',
            'properties': {
                'member': {'type': 'object'}
            }
        },
        400: {'description': 'Invalid input or cannot change owner role'},
        403: {'description': 'Permission denied'},
        404: {'description': 'Member not found'}
    }
)
@api_view(['PUT', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
async def workspace_member_detail(request, id, userId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=id)
        member = get_object_or_404(WorkspaceMember, workspace=workspace, user_id=userId)

        if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
            return Response({'error': 'Only owners and admins can manage members'}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'PUT':
            update_data = {}
            for key, value in request.data.items():
                if value is not None and value != '':
                    update_data[key] = value

            # If editing an Owner, strip out role changes to preserve Owner status
            if member.role == 'Owner' and 'role' in update_data:
                del update_data['role']

            serializer = WorkspaceMemberSerializer(member, data=update_data, partial=True)
            if serializer.is_valid():
                old_values = {k: getattr(member, k, None) for k in update_data.keys()}
                serializer.save()

                # Also update the User model fields so changes reflect in the UI
                user_obj = member.user
                user_changed = False
                if 'name' in update_data and update_data['name']:
                    name_parts = update_data['name'].strip().split(' ', 1)
                    user_obj.first_name = name_parts[0]
                    user_obj.last_name = name_parts[1] if len(name_parts) > 1 else ''
                    user_changed = True
                if 'phone' in update_data:
                    user_obj.phone = update_data['phone']
                    user_changed = True
                if user_changed:
                    user_obj.save()

                create_workspace_log(
                    workspace=workspace,
                    user=request.user,
                    log_type='team_update',
                    action='member_update',
                    description=f"Updated member {member.user.email} in workspace",
                    entity_type='member',
                    entity_id=member.id,
                    metadata={'member_email': member.user.email, 'updated_fields': list(update_data.keys())},
                    request=request
                )

                create_audit_log(
                    workspace=workspace,
                    user=request.user,
                    action='update',
                    entity_type='member',
                    entity_id=member.id,
                    old_values=old_values,
                    new_values=update_data,
                    request=request
                )

                create_notification(
                    user=member.user,
                    workspace=workspace,
                    action=f"Role Updated in {workspace.name}",
                    description=f"Your role has been updated. New role: {member.role}",
                    note_type="workspace_access",
                    severity="info",
                    triggered_by=request.user
                )

                create_user_activity_log(user=request.user, activity_type='api_request', workspace=workspace, module='workspaces', request=request)

                return Response({'member': serializer.data})
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        elif request.method == 'DELETE':
            if member.role == 'Owner' and request.user.id != member.user.id:
                return Response({'error': 'Only the workspace owner can remove themselves'}, status=status.HTTP_403_FORBIDDEN)

            member_email = member.user.email
            member_user_id = member.user.id
            member_id = member.id
            old_values = {'user_email': member.user.email, 'role': member.role}
            member_user_obj = member.user
            member.delete()

            from .tasks import send_workspace_member_removed_email
            send_workspace_member_removed_email.delay(
                str(member_user_id),
                str(workspace.id),
                workspace.name,
                request.user.email,
            )

            create_workspace_log(
                workspace=workspace,
                user=request.user,
                log_type='team_update',
                action='member_remove',
                description=f"Removed member {member_email} from workspace",
                entity_type='member',
                entity_id=member_id,
                metadata={'member_email': member_email},
                request=request
            )

            create_audit_log(
                workspace=workspace,
                user=request.user,
                action='delete',
                entity_type='member',
                entity_id=member_id,
                old_values=old_values,
                request=request
            )

            create_notification(
                user=member_user_obj,
                workspace=workspace,
                action=f"Removed from Workspace: {workspace.name}",
                description=f"You have been removed from {workspace.name}",
                note_type="workspace_access",
                severity="warning",
                triggered_by=request.user
            )

            create_user_activity_log(user=request.user, activity_type='api_request', workspace=workspace, module='workspaces', request=request)

            return Response({'message': 'Member removed successfully'})

    return await _sync_logic()

@extend_schema(
    tags=["Workspaces"],
    summary="Workspace Invitations",
    description="GET: List workspace invitations. POST: Send new invitation",
    parameters=[
        {
            'name': 'Status',
            'in': 'query',
            'description': 'Filter by invitation status',
            'required': False,
            'schema': {
                'type': 'string',
                'enum': ['pending', 'accepted', 'declined', 'expired']
            }
        },
        {
            'name': 'Page',
            'in': 'query',
            'description': 'Page number',
            'required': False,
            'schema': {'type': 'integer', 'default': 1}
        },
        {
            'name': 'PageSize',
            'in': 'query',
            'description': 'Number of items per page',
            'required': False,
            'schema': {'type': 'integer', 'default': 20}
        }
    ],
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'email': {'type': 'string', 'description': 'Invitee email'},
                'role': {'type': 'string', 'enum': ['Admin', 'Member'], 'description': 'Invitation role'},
                'phone': {'type': 'string', 'description': 'Phone number'},
                'job_role': {'type': 'string', 'description': 'Job role'}
            },
            'required': ['email', 'role']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'email': {'type': 'string', 'description': 'Invitee email'},
                'role': {'type': 'string', 'enum': ['Admin', 'Member'], 'description': 'Invitation role'},
                'phone': {'type': 'string', 'description': 'Phone number'},
                'job_role': {'type': 'string', 'description': 'Job role'}
            },
            'required': ['email', 'role']
        }
    },
    responses={
        200: {
            'description': 'List of invitations',
            'type': 'object',
            'properties': {
                'data': {'type': 'array'},
                'pagination': {'type': 'object'}
            }
        },
        201: {
            'description': 'Invitation sent',
            'type': 'object',
            'properties': {
                'invitation': {'type': 'object'}
            }
        },
        400: {'description': 'Invalid input'},
        402: {'description': 'User limit would be exceeded'},
        403: {'description': 'Permission denied'}
    }
)
@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
async def workspace_invitations(request, id):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=id)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'GET':
            invitations = workspace.invitations.all().select_related('invited_by', 'workspace')
            status_filter = request.GET.get('Status')

            if status_filter:
                invitations = invitations.filter(status=status_filter)

            paginator = StandardResultsSetPagination()
            page = paginator.paginate_queryset(invitations, request)

            serializer = WorkspaceInvitationSerializer(page, many=True)

            return paginator.get_paginated_response({
                'data': serializer.data,
                'pagination': {
                    'page': paginator.page.number,
                    'page_size': paginator.page_size,
                    'total_pages': paginator.page.paginator.num_pages,
                    'total_count': paginator.page.paginator.count
                }
            })

        elif request.method == 'POST':
            if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
                return Response({'error': 'Only owners and admins can send invitations'}, status=status.HTTP_403_FORBIDDEN)

            email = sanitize_input(request.data.get('email', ''), 254).lower()

            if not email:
                return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)

            existing_invitation = WorkspaceInvitation.objects.filter(
                workspace=workspace,
                email=email,
                status='pending'
            ).first()

            if existing_invitation:
                return Response({
                    'error': f'An invitation has already been sent to {email} for this workspace'
                }, status=status.HTTP_400_BAD_REQUEST)


            from django.contrib.auth import get_user_model
            User = get_user_model()

            try:
                invitee_user = User.objects.get(email=email)

                if WorkspaceMember.objects.filter(workspace=workspace, user=invitee_user).exists():
                    return Response({
                        'error': f'User {email} is already a member of this workspace'
                    }, status=status.HTTP_400_BAD_REQUEST)
            except User.DoesNotExist:
                # User doesn't exist - they'll need to register first
                pass


            from organizations.user_org_views import calculate_user_stats, get_plan_limits
            current_usage = calculate_user_stats(workspace.owner)
            limits = get_plan_limits(workspace.owner.plan_type)

            if current_usage['total_potential_users'] >= limits['max_users']:
                return Response(
                    {'error': f"User limit exceeded for your plan. You have {current_usage['user_count']} members and {current_usage['pending_invitation_count']} pending invitations (Limit: {limits['max_users']})."}, 
                    status=status.HTTP_402_PAYMENT_REQUIRED
                )

            serializer = WorkspaceInvitationSerializer(data=request.data)
            if serializer.is_valid():
                token = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))


                invitation_data = serializer.validated_data.copy()

                invitation = WorkspaceInvitation.objects.create(
                    workspace=workspace,
                    invited_by=request.user,
                    token=token,
                    expires_at=timezone.now() + timedelta(days=7),
                    **invitation_data
                )


                from .tasks import send_workspace_invitation_email
                send_workspace_invitation_email.delay(str(invitation.id))

                create_workspace_log(
                    workspace=workspace,
                    user=request.user,
                    log_type='team_update',
                    action='invite',
                    description=f"Invited {invitation.email} to workspace",
                    entity_type='invitation',
                    entity_id=invitation.id,
                    metadata={'email': invitation.email, 'role': invitation.role},
                    request=request
                )

                return Response(
                    {'invitation': WorkspaceInvitationSerializer(invitation).data},
                    status=status.HTTP_201_CREATED
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    return await _sync_logic()

@extend_schema(
    tags=["Workspaces"],
    summary="Workspace Invitation Detail",
    description="PUT: Accept/decline invitation. DELETE: Delete invitation",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'status': {'type': 'string', 'enum': ['accepted', 'declined'], 'description': 'Invitation status'}
            },
            'required': ['status']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'status': {'type': 'string', 'enum': ['accepted', 'declined'], 'description': 'Invitation status'}
            },
            'required': ['status']
        }
    },
    responses={
        200: {
            'type': 'object',
            'properties': {
                'invitation': {'type': 'object'},
                'message': {'type': 'string'}
            }
        },
        400: {'description': 'Invalid status or invitation already processed/expired'},
        403: {'description': 'Permission denied'},
        404: {'description': 'Invitation not found'}
    }
)
@api_view(['PUT', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
async def workspace_invitation_detail(request, id, invitationId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=id)
        invitation = get_object_or_404(WorkspaceInvitation, id=invitationId, workspace=workspace)

        if request.method == 'PUT':
            new_status = request.data.get('status')
            if new_status not in ['accepted', 'declined']:
                return Response({'error': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)

            if invitation.status != 'pending':
                return Response({'error': 'Invitation already processed'}, status=status.HTTP_400_BAD_REQUEST)

            if invitation.is_expired():
                invitation.status = 'expired'
                invitation.save()
                return Response({'error': 'Invitation has expired'}, status=status.HTTP_400_BAD_REQUEST)

            if new_status == 'accepted':
                # Security Fix: Verify that the authenticated user's email matches the invitation email
                if invitation.email.lower() != request.user.email.lower():
                    return Response(
                        {'error': 'This invitation was sent to a different email address. Please log in with the correct account.'}, 
                        status=status.HTTP_403_FORBIDDEN
                    )

            invitation.status = new_status
            invitation.save()

            if new_status == 'accepted':
                new_member = WorkspaceMember.objects.create(
                    workspace=workspace,
                    user=request.user,
                    role=invitation.role,
                    phone=invitation.phone,
                    job_role=invitation.job_role,
                    user_status=invitation.user_status,
                    email=request.user.email
                )

                create_workspace_log(
                    workspace=workspace,
                    user=request.user,
                    log_type='member_add',
                    action='join',
                    description=f"Joined workspace: {workspace.name}",
                    entity_type='workspace',
                    entity_id=workspace.id,
                    metadata={'workspace_name': workspace.name, 'role': invitation.role},
                    request=request
                )

                # Notify workspace admins/owner
                admins = WorkspaceMember.objects.filter(workspace=workspace, role__in=['Owner', 'Admin']).select_related('user')
                for admin in admins:
                    if admin.user and admin.user != request.user:
                        create_notification(
                            user=admin.user,
                            workspace=workspace,
                            action=f"New Member Joined: {workspace.name}",
                            description=f"{request.user.first_name or request.user.email} joined the workspace",
                            note_type="member_join",
                            severity="success",
                            triggered_by=request.user
                        )

            return Response({'invitation': WorkspaceInvitationSerializer(invitation).data})

        elif request.method == 'DELETE':
            if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
                return Response({'error': 'Only owners and admins can delete invitations'}, status=status.HTTP_403_FORBIDDEN)

            invitation.delete()
            return Response({'message': 'Invitation deleted successfully'})

    return await _sync_logic()

@extend_schema(
    tags=["Workspaces"],
    summary="Accept Workspace Invitation",
    description="Accept a workspace invitation using token",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'token': {'type': 'string', 'description': 'Invitation token'}
            },
            'required': ['token']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'token': {'type': 'string', 'description': 'Invitation token'}
            },
            'required': ['token']
        }
    },
    responses={
        200: {
            'type': 'object',
            'properties': {
                'workspace': {'type': 'object'},
                'message': {'type': 'string'}
            }
        },
        400: {'description': 'Invalid or expired invitation token'},
        401: {'description': 'Authentication required'}
    }
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
async def accept_workspace_invitation(request):
    @sync_to_async
    def _sync_logic():
        from django.db import transaction

        token = request.data.get('token')

        if not token:
            return Response({'error': 'Invitation token required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            invitation = WorkspaceInvitation.objects.get(token=token)

            if not invitation.is_valid():
                return Response({'error': 'Invalid or expired invitation'}, status=status.HTTP_400_BAD_REQUEST)

            if invitation.email.lower() != request.user.email.lower():
                return Response({'error': 'This invitation is not for your email address'}, status=status.HTTP_400_BAD_REQUEST)

            if WorkspaceMember.objects.filter(workspace=invitation.workspace, user=request.user).exists():
                return Response({'error': 'You are already a member of this workspace'}, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                WorkspaceMember.objects.create(
                    workspace=invitation.workspace,
                    user=request.user,
                    role=invitation.role,
                    phone=invitation.phone,
                    job_role=invitation.job_role,
                    user_status=invitation.user_status,
                    email=request.user.email
                )

                invitation.status = 'accepted'
                invitation.save()

                create_workspace_log(
                    workspace=invitation.workspace,
                    user=request.user,
                    log_type='member_add',
                    action='join',
                    description=f"Joined workspace: {invitation.workspace.name}",
                    entity_type='workspace',
                    entity_id=invitation.workspace.id,
                    metadata={'workspace_name': invitation.workspace.name, 'role': invitation.role},
                    request=request
                )

                # Notify workspace admins/owner
                admins = WorkspaceMember.objects.filter(workspace=invitation.workspace, role__in=['Owner', 'Admin']).select_related('user')
                for admin in admins:
                    if admin.user and admin.user != request.user:
                        create_notification(
                            user=admin.user,
                            workspace=invitation.workspace,
                            action=f"New Member Joined: {invitation.workspace.name}",
                            description=f"{request.user.first_name or request.user.email} joined the workspace",
                            note_type="member_join",
                            severity="success",
                            triggered_by=request.user
                        )

            return Response({
                'workspace': WorkspaceSerializer(invitation.workspace, context={'request': request}).data,
                'message': 'Successfully joined workspace'
            })

        except WorkspaceInvitation.DoesNotExist:
            return Response({'error': 'Invalid invitation token'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': f'Failed to accept invitation: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return await _sync_logic()

@extend_schema(
    tags=["Workspaces"],
    summary="Get Invitation Details",
    description="Get invitation details using token (for unregistered users)",
    responses={
        200: {
            'type': 'object',
            'properties': {
                'invitation': {'type': 'object'},
                'workspace': {'type': 'object'},
                'user_exists': {'type': 'boolean'},
                'registration_required': {'type': 'boolean'}
            }
        },
        400: {'description': 'Invalid or expired invitation'},
        404: {'description': 'Invitation not found'}
    }
)
@api_view(['GET'])
@permission_classes([permissions.AllowAny])
async def get_invitation_details(request, token):
    @sync_to_async
    def _sync_logic():
        """
        GET /api/workspaces/invitations/{token}/details
        Get invitation details for both registered and unregistered users
        """
        try:
            invitation = WorkspaceInvitation.objects.get(token=token)

            if not invitation.is_valid():
                return Response({
                    'error': 'Invalid or expired invitation',
                    'expired': invitation.is_expired(),
                    'status': invitation.status
                }, status=status.HTTP_400_BAD_REQUEST)

            from django.contrib.auth import get_user_model
            User = get_user_model()

            try:
                User.objects.get(email=invitation.email)
                user_exists = True
                registration_required = False
            except User.DoesNotExist:
                user_exists = False
                registration_required = True

            return Response({
                'invitation': {
                    'id': str(invitation.id),
                    'email': invitation.email,
                    'role': invitation.role,
                    'phone': invitation.phone,
                    'job_role': invitation.job_role,
                    'expires_at': invitation.expires_at,
                    'invited_by': invitation.invited_by.email
                },
                'workspace': {
                    'id': str(invitation.workspace.id),
                    'name': invitation.workspace.name,
                    'description': invitation.workspace.description,
                    'type': invitation.workspace.type
                },
                'user_exists': user_exists,
                'registration_required': registration_required
            })

        except WorkspaceInvitation.DoesNotExist:
            return Response({'error': 'Invalid invitation token'}, status=status.HTTP_404_NOT_FOUND)

    return await _sync_logic()

@extend_schema(
    tags=["Workspaces"],
    summary="Workspace Settings",
    description="GET: Get workspace settings and permissions. PUT: Update workspace settings",
    responses={200: {'description': 'Workspace settings and permissions'}}
)
@api_view(['GET', 'PUT'])
@permission_classes([permissions.IsAuthenticated])
async def workspace_settings(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        # Get or create workspace settings
        settings_obj, created = WorkspaceSettings.objects.get_or_create(workspace=workspace)

        if request.method == 'GET':
            # Check cache first
            cache_key = f"workspace_settings_{workspaceId}_{request.user.id}"
            cached_data = cache.get(cache_key)
            if cached_data:
                return Response(cached_data)

            # Get user's role for permissions
            try:
                member = WorkspaceMember.objects.get(workspace=workspace, user=request.user)
                user_role = member.role
            except WorkspaceMember.DoesNotExist:
                user_role = None

            permissions_data = {
                'can_edit_settings': user_role in ['Owner', 'Admin'],
                'can_manage_members': user_role in ['Owner', 'Admin'],
                'can_create_tasks': user_role in ['Owner', 'Admin', 'Member'],
                'can_delete_workspace': user_role == 'Owner',
                'can_create_backups': user_role in ['Owner', 'Admin']
            }

            from .serializers import WorkspaceSettingsSerializer

            response_data = {
                'settings': WorkspaceSettingsSerializer(settings_obj).data,
                'permissions': permissions_data
            }

            # Cache for 5 minutes
            cache.set(cache_key, response_data, 300)
            return Response(response_data)

        elif request.method == 'PUT':
            # Only owners and admins can update settings
            if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
                return Response({'error': 'Only workspace owners and admins can update settings'}, status=status.HTTP_403_FORBIDDEN)

            from .serializers import WorkspaceSettingsUpdateSerializer

            serializer = WorkspaceSettingsUpdateSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            # Explicit check for enabled_modules change
            if 'enabled_modules' in serializer.validated_data:
                try:
                    member = WorkspaceMember.objects.get(workspace=workspace, user=request.user)
                    if member.role != 'Owner':
                        return Response({'error': 'Only the workspace owner can toggle modules'}, status=status.HTTP_403_FORBIDDEN)
                except WorkspaceMember.DoesNotExist:
                    return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

            # Update settings
            for field, value in serializer.validated_data.items():
                setattr(settings_obj, field, value)

            settings_obj.save()

            # Clear cache
            cache.delete(f"workspace_settings_{workspaceId}_{request.user.id}")

            from .serializers import WorkspaceSettingsSerializer
            return Response({
                'settings': WorkspaceSettingsSerializer(settings_obj).data
            })
    return await _sync_logic()

