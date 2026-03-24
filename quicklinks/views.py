from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework import status, permissions
from rest_framework.decorators import permission_classes, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from cachalot.api import cachalot_disabled

from .models import QuickLink, QuickLinkCategory, SharedQuickLink, RecentItem
from .serializers import (
    QuickLinkSerializer, QuickLinkCreateSerializer, QuickLinkCategorySerializer,
    SharedQuickLinkSerializer, SharedQuickLinkCreateSerializer,
    RecentItemSerializer, RecentItemCreateSerializer, FrequentItemSerializer
)
from workspaces.models import Workspace
from utils import check_workspace_permission

def check_user_permission(request_user, target_user_id):
    """Check if request user can access target user's data"""
    return str(request_user.id) == str(target_user_id)

@extend_schema(
    tags=["Quick Links"],
    summary="User Quick Links",
    description="GET: List user's quick links with categories and recent items. POST: Create new quick link",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'title': {'type': 'string'},
                'url': {'type': 'string'},
                'icon': {'type': 'string'},
                'category': {'type': 'string'},
                'workspace_id': {'type': 'string'},
                'entity_type': {'type': 'string', 'enum': ['task', 'wiki', 'integration', 'custom']},
                'entity_id': {'type': 'string'}
            },
            'required': ['title', 'url']
        }
    },
    responses={
        200: {'description': 'Quick links data'},
        201: {'description': 'Quick link created'}
    }
)
@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def user_quick_links(request, userId):
    @sync_to_async
    def _sync_logic():
        if not check_user_permission(request.user, userId):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'GET':
            with cachalot_disabled():
                quick_links = QuickLink.objects.filter(user=request.user)
                    
                categories = QuickLinkCategory.objects.filter(user=request.user)
                recent_items = RecentItem.objects.filter(user=request.user)[:10]

                data = {
                    'quick_links': QuickLinkSerializer(quick_links, many=True).data,
                    'categories': QuickLinkCategorySerializer(categories, many=True).data,
                    'recent_items': RecentItemSerializer(recent_items, many=True).data
                }

            response = Response(data)
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            return response

        elif request.method == 'POST':
            serializer = QuickLinkCreateSerializer(data=request.data, context={'request': request})
            if serializer.is_valid():
                quick_link = serializer.save()
                return Response({
                    'quick_link': QuickLinkSerializer(quick_link).data
                }, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    return await _sync_logic()

@extend_schema(
    tags=["Quick Links"],
    summary="Quick Link Detail",
    description="PUT: Update quick link. DELETE: Delete quick link",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'title': {'type': 'string'},
                'url': {'type': 'string'},
                'icon': {'type': 'string'},
                'category': {'type': 'string'},
                'is_pinned': {'type': 'boolean'},
                'sort_order': {'type': 'integer'}
            }
        }
    },
    responses={200: {'description': 'Quick link updated'}}
)
@api_view(['PUT', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def quick_link_detail(request, userId, id):
    @sync_to_async
    def _sync_logic():
        if not check_user_permission(request.user, userId):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        quick_link = get_object_or_404(QuickLink, id=id, user=request.user)

        if request.method == 'PUT':
            update_data = {}
            for key, value in request.data.items():
                if value is not None and value != '':
                    update_data[key] = value

            serializer = QuickLinkSerializer(quick_link, data=update_data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response({'quick_link': serializer.data})
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        elif request.method == 'DELETE':
            quick_link.delete()
            return Response({'message': 'Quick link deleted successfully'})

    return await _sync_logic()

@extend_schema(
    tags=["Quick Links"],
    summary="Reorder Quick Links",
    description="Reorder user's quick links",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'quick_link_ids': {'type': 'array', 'items': {'type': 'string'}}
            },
            'required': ['quick_link_ids']
        }
    },
    responses={200: {'description': 'Quick links reordered'}}
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def reorder_quick_links(request, userId):
    @sync_to_async
    def _sync_logic():
        if not check_user_permission(request.user, userId):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        quick_link_ids = request.data.get('quick_link_ids', [])

        for index, link_id in enumerate(quick_link_ids):
            QuickLink.objects.filter(id=link_id, user=request.user).update(sort_order=index)

        quick_links = QuickLink.objects.filter(user=request.user)
        return Response({
            'quick_links': QuickLinkSerializer(quick_links, many=True).data
        })

    return await _sync_logic()

@extend_schema(
    tags=["Quick Links"],
    summary="Workspace Shared Quick Links",
    description="GET: List shared quick links. POST: Create shared quick link",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'title': {'type': 'string'},
                'url': {'type': 'string'},
                'description': {'type': 'string'},
                'icon': {'type': 'string'},
                'category': {'type': 'string'},
                'visibility': {'type': 'string', 'enum': ['all_members', 'admins_only']}
            },
            'required': ['title', 'url', 'category', 'visibility']
        }
    },
    responses={
        200: {'description': 'Shared quick links'},
        201: {'description': 'Shared quick link created'}
    }
)
@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def workspace_shared_links(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'GET':
            with cachalot_disabled():
                shared_links = workspace.shared_quick_links.all()

                if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
                    shared_links = shared_links.filter(visibility='all_members')

                data = {
                    'shared_links': SharedQuickLinkSerializer(shared_links, many=True).data,
                    'workspace_shortcuts': []  # Can be extended for workspace-specific shortcuts
                }

            response = Response(data)
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            return response

        elif request.method == 'POST':
            if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
                return Response({'error': 'Only owners and admins can create shared quick links'}, status=status.HTTP_403_FORBIDDEN)

            serializer = SharedQuickLinkCreateSerializer(data=request.data, context={'workspace': workspace, 'request': request})
            if serializer.is_valid():
                shared_link = serializer.save()
                return Response({
                    'shared_link': SharedQuickLinkSerializer(shared_link).data
                }, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    return await _sync_logic()

@extend_schema(
    tags=["Quick Links"],
    summary="Workspace Shared Quick Link Detail",
    description="PUT: Update a shared quick link. DELETE: Delete a shared quick link",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'title': {'type': 'string'},
                'url': {'type': 'string'},
                'description': {'type': 'string'},
                'icon': {'type': 'string'},
                'category': {'type': 'string'},
                'visibility': {'type': 'string', 'enum': ['all_members', 'admins_only']}
            }
        }
    },
    responses={200: {'description': 'Shared quick link updated / deleted'}}
)
@api_view(['PUT', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def workspace_shared_link_detail(request, workspaceId, id):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
            return Response({'error': 'Only owners and admins can modify shared quick links'}, status=status.HTTP_403_FORBIDDEN)

        shared_link = get_object_or_404(SharedQuickLink, id=id, workspace=workspace)

        if request.method == 'PUT':
            update_data = {k: v for k, v in request.data.items() if v is not None and v != ''}
            serializer = SharedQuickLinkSerializer(shared_link, data=update_data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response({'shared_link': serializer.data})
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        elif request.method == 'DELETE':
            shared_link.delete()
            return Response({'message': 'Shared quick link deleted successfully'})

    return await _sync_logic()

@extend_schema(
    tags=["Quick Links"],
    summary="User Recent Items",
    description="GET: List recent items. POST: Track item access",
    parameters=[
        {'name': 'ItemType', 'in': 'query', 'schema': {'type': 'string'}},
        {'name': 'Limit', 'in': 'query', 'schema': {'type': 'integer', 'default': 10}},
        {'name': 'WorkspaceId', 'in': 'query', 'schema': {'type': 'string'}},
    ],
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'item_type': {'type': 'string', 'enum': ['task', 'wiki', 'workspace', 'integration']},
                'item_id': {'type': 'string'},
                'workspace_id': {'type': 'string'},
                'action': {'type': 'string', 'enum': ['viewed', 'edited', 'created']}
            },
            'required': ['item_type', 'item_id', 'action']
        }
    },
    responses={
        200: {'description': 'Recent items'},
        201: {'description': 'Recent item tracked'}
    }
)
@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def user_recent_items(request, userId):
    @sync_to_async
    def _sync_logic():
        if not check_user_permission(request.user, userId):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'GET':
            with cachalot_disabled():
                recent_items = RecentItem.objects.filter(user=request.user)

                item_type = request.GET.get('ItemType')
                if item_type:
                    recent_items = recent_items.filter(item_type=item_type)

                workspace_id = request.GET.get('WorkspaceId')
                if workspace_id:
                    recent_items = recent_items.filter(workspace_id=workspace_id)

                limit = int(request.GET.get('Limit', 10))
                recent_items = recent_items[:limit]

                frequent_items = RecentItem.objects.filter(
                    user=request.user,
                    access_count__gte=3
                ).order_by('-access_count')[:5]

                data = {
                    'recent_items': RecentItemSerializer(recent_items, many=True).data,
                    'frequently_accessed': FrequentItemSerializer(frequent_items, many=True).data
                }

            response = Response(data)
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            return response

        elif request.method == 'POST':
            serializer = RecentItemCreateSerializer(data=request.data, context={'request': request})
            if serializer.is_valid():
                recent_item = serializer.save()
                return Response({
                    'recent_item': RecentItemSerializer(recent_item).data
                }, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    return await _sync_logic()

