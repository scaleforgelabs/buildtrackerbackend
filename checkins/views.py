from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework import status, permissions
from rest_framework.decorators import permission_classes, parser_classes
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from cachalot.api import cachalot_disabled
from drf_spectacular.utils import extend_schema

from .models import DailyCheckIn
from .serializers import DailyCheckInCreateSerializer, DailyCheckInFeedSerializer
from workspaces.models import Workspace, WorkspaceMember
from utils import check_workspace_permission


@extend_schema(
    tags=["Check-ins"],
    summary="Workspace Daily Check-ins",
    description=(
        "GET: Returns today's check-ins from all members in the workspace (the team feed). "
        "POST: Submit your daily check-in. One submission per user per workspace per day is allowed."
    ),
)
@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser])
async def workspace_checkins(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response(
                {'error': 'Permission denied. You must be a member of this workspace.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if request.method == 'GET':
            with cachalot_disabled():
                today = timezone.now().date()
                checkins = (
                    DailyCheckIn.objects
                    .filter(workspace=workspace)
                    .select_related('user')
                    .prefetch_related('yesterday_tasks', 'tomorrow_tasks', 'blockers__notify_member')
                    .order_by('-created_at')
                )[:50]
                # Optimization: Pre-fetch member roles to avoid N+1 queries in serializer
                member_roles = {
                    m.user_id: (m.job_role or m.role or '') 
                    for m in WorkspaceMember.objects.filter(workspace=workspace)
                }

                serializer = DailyCheckInFeedSerializer(
                    checkins, 
                    many=True, 
                    context={'request': request, 'member_roles': member_roles}
                )
            response = Response({'checkins': serializer.data})
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            return response

        elif request.method == 'POST':
            serializer = DailyCheckInCreateSerializer(
                data=request.data,
                context={'workspace': workspace, 'request': request}
            )
            if serializer.is_valid():
                checkin = serializer.save()
                # Fetch individual member role for single item return
                try:
                    m = WorkspaceMember.objects.get(workspace=workspace, user=checkin.user)
                    role = m.job_role or m.role or ''
                except WorkspaceMember.DoesNotExist:
                    role = ''
                
                feed_serializer = DailyCheckInFeedSerializer(
                    checkin, 
                    context={'request': request, 'member_roles': {checkin.user_id: role}}
                )
                return Response(
                    {'checkin': feed_serializer.data},
                    status=status.HTTP_201_CREATED
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    return await _sync_logic()


@extend_schema(
    tags=["Check-ins"],
    summary="My Check-in History",
    description="Returns the current user's check-in history for this workspace, ordered most recent first.",
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser])
async def my_checkins(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response(
                {'error': 'Permission denied. You must be a member of this workspace.'},
                status=status.HTTP_403_FORBIDDEN
            )

        with cachalot_disabled():
            checkins = (
                DailyCheckIn.objects
                .filter(workspace=workspace, user=request.user)
                .select_related('user')
                .prefetch_related('yesterday_tasks', 'tomorrow_tasks', 'blockers__notify_member')
                .order_by('-created_at')
            )
            # Optimization: Pre-fetch member roles
            member_roles = {
                m.user_id: (m.job_role or m.role or '') 
                for m in WorkspaceMember.objects.filter(workspace=workspace)
            }

            serializer = DailyCheckInFeedSerializer(
                checkins, 
                many=True, 
                context={'request': request, 'member_roles': member_roles}
            )

        response = Response({'checkins': serializer.data})
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return response

    return await _sync_logic()


@extend_schema(
    tags=["Check-ins"],
    summary="Today's Check-in Status",
    description="Returns whether the current user has already submitted a check-in today for this workspace.",
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser])
async def checkin_status(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response(
                {'error': 'Permission denied.'},
                status=status.HTTP_403_FORBIDDEN
            )

        days_str = request.GET.get('days', '7')
        try:
            days = int(days_str)
        except ValueError:
            days = 7

        today = timezone.now().date()
        start_date = today - timezone.timedelta(days=days)

        submitted_dates = set(
            DailyCheckIn.objects.filter(
                workspace=workspace, 
                user=request.user, 
                date__gt=start_date,
                date__lte=today
            ).values_list('date', flat=True)
        )

        missed_dates = []
        for i in range(1, days + 1):
            d = today - timezone.timedelta(days=i)
            if d not in submitted_dates:
                missed_dates.append(d.strftime('%A, %b %d'))

        missed_days = len(missed_dates)

        submitted = DailyCheckIn.objects.filter(
            workspace=workspace, user=request.user, date=today
        ).exists()

        return Response({
            'submitted_today': submitted, 
            'missed_days': missed_days,
            'missed_dates': missed_dates
        })

    return await _sync_logic()
