from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework import status, permissions
from rest_framework.decorators import permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from datetime import datetime

from .models import Notification
from .serializers import NotificationSerializer, NotificationCreateSerializer
from workspaces.models import Workspace
from utils import sanitize_input

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'PageSize'
    max_page_size = 100
    page_query_param = 'Page'

def get_filtered_notifications(queryset, request):
    search_key = request.GET.get('SearchKey')
    status_filter = request.GET.get('Status')
    severity_filter = request.GET.get('Severity')
    date_from = request.GET.get('DateFrom')
    sort_column = request.GET.get('SortColumn', 'created_at')
    sort_order = request.GET.get('SortOrder', 'desc')
    
    if search_key:
        search_key = sanitize_input(search_key)
        queryset = queryset.filter(
            Q(action__icontains=search_key) |
            Q(description__icontains=search_key) |
            Q(note_type__icontains=search_key)
        )
    
    if status_filter:
        if status_filter == 'unread':
            queryset = queryset.filter(is_read=False)
        elif status_filter == 'read':
            queryset = queryset.filter(is_read=True)
    
    if severity_filter:
        queryset = queryset.filter(severity=severity_filter)
    
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
    tags=["Notifications"],
    summary="User Notifications",
    description="GET: List user notifications with filtering. POST: Create new notification",
    parameters=[
        {'name': 'Status', 'in': 'query', 'schema': {'type': 'string', 'enum': ['read', 'unread']}},
        {'name': 'Severity', 'in': 'query', 'schema': {'type': 'string', 'enum': ['info', 'success', 'warning', 'error']}},
        {'name': 'DateFrom', 'in': 'query', 'schema': {'type': 'string', 'format': 'date'}},
        {'name': 'SearchKey', 'in': 'query', 'schema': {'type': 'string'}},
        {'name': 'Page', 'in': 'query', 'schema': {'type': 'integer', 'default': 1}},
        {'name': 'PageSize', 'in': 'query', 'schema': {'type': 'integer', 'default': 20}},
        {'name': 'SortColumn', 'in': 'query', 'schema': {'type': 'string', 'default': 'created_at'}},
        {'name': 'SortOrder', 'in': 'query', 'schema': {'type': 'string', 'enum': ['asc', 'desc'], 'default': 'desc'}},
    ]
)
@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
async def notifications_list(request):
    @sync_to_async
    def _sync_logic():
        if request.method == 'GET':
            notifications = Notification.objects.filter(user=request.user)
            filtered_notifications = get_filtered_notifications(notifications, request)

            paginator = StandardResultsSetPagination()
            page = paginator.paginate_queryset(filtered_notifications, request)

            serializer = NotificationSerializer(page, many=True)

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
                    'severity': request.GET.get('Severity', ''),
                    'search_key': request.GET.get('SearchKey', ''),
                    'date_from': request.GET.get('DateFrom', ''),
                    'sort_column': request.GET.get('SortColumn', 'created_at'),
                    'sort_order': request.GET.get('SortOrder', 'desc')
                }
            })

        elif request.method == 'POST':
            serializer = NotificationCreateSerializer(data=request.data, context={'request': request})
            if serializer.is_valid():
                notification = serializer.save()
                return Response({
                    'notification': NotificationSerializer(notification).data
                }, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    return await _sync_logic()

@extend_schema(
    tags=["Notifications"],
    summary="Mark Notification as Read",
    description="Mark a specific notification as read"
)
@api_view(['PUT'])
@permission_classes([permissions.IsAuthenticated])
async def mark_notification_read(request, id):
    @sync_to_async
    def _sync_logic():
        notification = get_object_or_404(Notification, id=id, user=request.user)

        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save()

        return Response({
            'notification': NotificationSerializer(notification).data
        })

    return await _sync_logic()

@extend_schema(
    tags=["Notifications"],
    summary="Delete Notification",
    description="Delete a specific notification"
)
@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
async def delete_notification(request, id):
    @sync_to_async
    def _sync_logic():
        notification = get_object_or_404(Notification, id=id, user=request.user)
        notification.delete()

        return Response({
            'message': 'Notification deleted successfully'
        })

    return await _sync_logic()

@extend_schema(
    tags=["Notifications"],
    summary="Mark All Notifications as Read",
    description="Mark all user notifications as read"
)
@api_view(['PUT'])
@permission_classes([permissions.IsAuthenticated])
async def mark_all_read(request):
    @sync_to_async
    def _sync_logic():
        count = Notification.objects.filter(user=request.user, is_read=False).update(
            is_read=True,
            read_at=timezone.now()
        )

        return Response({
            'message': 'All notifications marked as read',
            'count': count
        })

    return await _sync_logic()

@extend_schema(
    tags=["Notifications"],
    summary="Unread Notifications Count",
    description="Get count of unread notifications"
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def unread_count(request):
    @sync_to_async
    def _sync_logic():
        count = Notification.objects.filter(user=request.user, is_read=False).count()

        return Response({
            'count': count
        })

    return await _sync_logic()

@extend_schema(
    tags=["Notifications"],
    summary="Workspace Notifications",
    description="Get notifications for a specific workspace"
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def workspace_notifications(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        notifications = Notification.objects.filter(user=request.user, workspace=workspace)
        filtered_notifications = get_filtered_notifications(notifications, request)

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(filtered_notifications, request)

        serializer = NotificationSerializer(page, many=True)

        return paginator.get_paginated_response({
            'data': serializer.data,
            'pagination': {
                'page': paginator.page.number,
                'page_size': paginator.page_size,
                'total_pages': paginator.page.paginator.num_pages,
                'total_count': paginator.page.paginator.count
            }
        })
    return await _sync_logic()

