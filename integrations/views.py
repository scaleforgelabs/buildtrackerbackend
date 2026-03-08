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
from cachalot.api import cachalot_disabled

from .models import Integration
from .serializers import IntegrationSerializer, IntegrationCreateSerializer, UserSerializer
from workspaces.models import Workspace, WorkspaceMember
from utils import sanitize_input, check_workspace_permission, create_workspace_log, create_audit_log, create_user_activity_log

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'PageSize'
    max_page_size = 100
    page_query_param = 'Page'

def get_filtered_integrations(queryset, request):
    search_key = request.GET.get('SearchKey')
    category = request.GET.get('Category')
    sort_column = request.GET.get('SortColumn', 'name')
    sort_order = request.GET.get('SortOrder', 'asc')
    
    if search_key:
        search_key = sanitize_input(search_key)
        queryset = queryset.filter(
            Q(name__icontains=search_key) |
            Q(description__icontains=search_key) |
            Q(category__icontains=search_key)
        )
    
    if category:
        queryset = queryset.filter(category__icontains=category)
    
    order_prefix = '-' if sort_order == 'desc' else ''
    queryset = queryset.order_by(f"{order_prefix}{sort_column}")
    
    return queryset

@extend_schema(
    tags=["Integrations"],
    summary="Integrations",
    description="GET: List integrations with filtering. POST: Create new integration",
    parameters=[
        {'name': 'SearchKey', 'in': 'query', 'schema': {'type': 'string'}},
        {'name': 'Category', 'in': 'query', 'schema': {'type': 'string'}},
        {'name': 'SortColumn', 'in': 'query', 'schema': {'type': 'string', 'default': 'name'}},
        {'name': 'SortOrder', 'in': 'query', 'schema': {'type': 'string', 'enum': ['asc', 'desc'], 'default': 'asc'}},
        {'name': 'Page', 'in': 'query', 'schema': {'type': 'integer', 'default': 1}},
        {'name': 'PageSize', 'in': 'query', 'schema': {'type': 'integer', 'default': 20}},
    ],
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string'},
                'icon': {'type': 'string'},
                'url': {'type': 'string'},
                'category': {'type': 'string'},
                'description': {'type': 'string'}
            },
            'required': ['name']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string'},
                'icon': {'type': 'string'},
                'url': {'type': 'string'},
                'category': {'type': 'string'},
                'description': {'type': 'string'}
            },
            'required': ['name']
        }
    },
    responses={
        200: {'description': 'List of integrations'},
        201: {'description': 'Integration created'}
    }
)
@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def integrations(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'GET':
            create_user_activity_log(user=request.user, activity_type='api_request', workspace=workspace, module='integrations', request=request)

            # Get user's role in the workspace
            try:
                member = WorkspaceMember.objects.get(workspace=workspace, user=request.user)
                role = member.role
            except WorkspaceMember.DoesNotExist:
                return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

            with cachalot_disabled():
                integrations_qs = workspace.integrations.all()

                # IDENTITY RESTRICTION: Only Admin, Owner, or Creator can see the integration
                if role not in ['Admin', 'Owner']:
                    integrations_qs = integrations_qs.filter(created_by=request.user)

                # VISIBILITY FILTER: "not visible when I click it"
                # Hide from list if is_visible is False, unless ShowAll=true is passed
                if request.GET.get('ShowAll') != 'true':
                    integrations_qs = integrations_qs.filter(is_visible=True)

                filtered_integrations = get_filtered_integrations(integrations_qs, request)


                paginator = StandardResultsSetPagination()
                page = paginator.paginate_queryset(filtered_integrations, request)

                serializer = IntegrationSerializer(page, many=True, context={'request': request})

            response = Response({
                'data': serializer.data,
                'pagination': {
                    'page': paginator.page.number,
                    'page_size': paginator.page_size,
                    'total_pages': paginator.page.paginator.num_pages,
                    'total_count': paginator.page.paginator.count
                },
                'filters': {
                    'search_key': request.GET.get('SearchKey', ''),
                    'category': request.GET.get('Category', ''),
                    'sort_column': request.GET.get('SortColumn', 'name'),
                    'sort_order': request.GET.get('SortOrder', 'asc')
                }
            })
            
            # Prevent caching at the browser/proxy level
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            return response

        elif request.method == 'POST':
            serializer = IntegrationCreateSerializer(data=request.data, context={'workspace': workspace, 'request': request})
            if serializer.is_valid():
                integration = serializer.save()

                create_workspace_log(
                    workspace=workspace,
                    user=request.user,
                    log_type='integration_create',
                    action='create',
                    description=f"Created integration: {integration.name}",
                    entity_type='integration',
                    entity_id=integration.id,
                    metadata={'integration_name': integration.name, 'category': integration.category},
                    request=request
                )

                create_audit_log(
                    workspace=workspace,
                    user=request.user,
                    action='create',
                    entity_type='integration',
                    entity_id=integration.id,
                    new_values={'integration_name': integration.name, 'category': integration.category},
                    request=request
                )

                create_user_activity_log(user=request.user, activity_type='api_request', workspace=workspace, module='integrations', request=request)

                return Response({
                    'integration': IntegrationSerializer(integration, context={'request': request}).data
                }, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    return await _sync_logic()

@extend_schema(
    tags=["Integrations"],
    summary="Integration Detail",
    description="GET: Get integration details. PUT: Update integration. DELETE: Delete integration",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string'},
                'icon': {'type': 'string'},
                'url': {'type': 'string'},
                'category': {'type': 'string'},
                'description': {'type': 'string'}
            }
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string'},
                'icon': {'type': 'string'},
                'url': {'type': 'string'},
                'category': {'type': 'string'},
                'description': {'type': 'string'}
            }
        }
    },
    responses={200: {'description': 'Integration details'}}
)
@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def integration_detail(request, workspaceId, id):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        integration = get_object_or_404(Integration, id=id, workspace=workspace)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        # IDENTITY RESTRICTION: Only Admin, Owner, or Creator can access details/modify
        member = get_object_or_404(WorkspaceMember, workspace=workspace, user=request.user)
        if not (member.role in ['Admin', 'Owner'] or integration.created_by == request.user):
            return Response({'error': 'Permission denied: Only Admins, Workspace Owners, or the Creator can access this integration.'}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'GET':
            create_user_activity_log(user=request.user, activity_type='api_request', workspace=workspace, module='integrations', request=request)

            serializer = IntegrationSerializer(integration, context={'request': request})
            return Response({
                'integration': serializer.data,
                'creator': UserSerializer(integration.created_by).data
            })

        elif request.method == 'PUT':
            # Filter out empty values
            update_data = {}
            for key, value in request.data.items():
                if value is not None and value != '':
                    update_data[key] = value

            serializer = IntegrationSerializer(integration, data=update_data, partial=True)
            if serializer.is_valid():
                old_values = {k: getattr(integration, k, None) for k in update_data.keys()}
                serializer.save()

                create_workspace_log(
                    workspace=workspace,
                    user=request.user,
                    log_type='integration_update',
                    action='update',
                    description=f"Updated integration: {integration.name}",
                    entity_type='integration',
                    entity_id=integration.id,
                    metadata={'integration_name': integration.name, 'updated_fields': list(update_data.keys())},
                    request=request
                )

                create_audit_log(
                    workspace=workspace,
                    user=request.user,
                    action='update',
                    entity_type='integration',
                    entity_id=integration.id,
                    old_values=old_values,
                    new_values=update_data,
                    request=request
                )

                create_user_activity_log(user=request.user, activity_type='api_request', workspace=workspace, module='integrations', request=request)

                return Response({'integration': serializer.data})
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        elif request.method == 'DELETE':
            integration_name = integration.name
            integration_id = integration.id
            old_values = {'integration_name': integration.name, 'category': integration.category}
            integration.delete()

            create_workspace_log(
                workspace=workspace,
                user=request.user,
                log_type='integration_delete',
                action='delete',
                description=f"Deleted integration: {integration_name}",
                entity_type='integration',
                entity_id=integration_id,
                metadata={'integration_name': integration_name},
                request=request
            )

            create_audit_log(
                workspace=workspace,
                user=request.user,
                action='delete',
                entity_type='integration',
                entity_id=integration_id,
                old_values=old_values,
                request=request
            )

            create_user_activity_log(user=request.user, activity_type='api_request', workspace=workspace, module='integrations', request=request)

            return Response({'message': 'Integration deleted successfully'})
    return await _sync_logic()

