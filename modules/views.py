from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework import status, permissions
from rest_framework.decorators import permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db.models import Count, Avg, Max, Sum
from django.utils import timezone
from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from datetime import datetime, timedelta

from .models import ModuleAccess, ModulePreferences
from .serializers import *
from workspaces.models import Workspace
from utils import check_workspace_permission
from rate_limiting import rate_limit, get_error_response

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'PageSize'
    max_page_size = 100
    page_query_param = 'Page'

@extend_schema(
    tags=["Modules"],
    summary="User Module Access",
    description="GET: List user module access logs. POST: Record module access",
    request=ModuleAccessCreateSerializer,
    responses={200: ModuleAccessSerializer(many=True), 201: ModuleAccessSerializer}
)
@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
@rate_limit(requests_per_minute=50)
async def user_module_access(request, userId):
    @sync_to_async
    def _sync_logic():
        if str(request.user.id) != str(userId) and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'GET':
            module_name = request.GET.get('ModuleName')
            date_from = request.GET.get('DateFrom')

            module_accesses = ModuleAccess.objects.filter(user_id=userId).select_related('workspace')

            if module_name:
                module_accesses = module_accesses.filter(module_name=module_name)

            if date_from:
                try:
                    date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                    module_accesses = module_accesses.filter(accessed_at__date__gte=date_from)
                except ValueError:
                    pass

            paginator = StandardResultsSetPagination()
            page = paginator.paginate_queryset(module_accesses, request)

            serializer = ModuleAccessSerializer(page, many=True)

            total_sessions = module_accesses.count()
            unique_modules = module_accesses.values('module_name').distinct().count()
            last_accessed = module_accesses.first().accessed_at if module_accesses.exists() else None

            return Response({
                'data': serializer.data,
                'pagination': {
                    'page': paginator.page.number,
                    'page_size': paginator.page_size,
                    'total_pages': paginator.page.paginator.num_pages,
                    'total_count': paginator.page.paginator.count
                },
                'total_sessions': total_sessions,
                'unique_modules': unique_modules,
                'last_accessed': last_accessed.isoformat() if last_accessed else None
            })

        elif request.method == 'POST':
            serializer = ModuleAccessCreateSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            data = serializer.validated_data
            workspace = None

            if data.get('workspace_id'):
                try:
                    workspace = Workspace.objects.get(id=data['workspace_id'])
                    if not check_workspace_permission(request.user, workspace):
                        return Response({'error': 'No access to specified workspace'}, status=status.HTTP_403_FORBIDDEN)
                except Workspace.DoesNotExist:
                    return Response({'error': 'Workspace not found'}, status=status.HTTP_404_NOT_FOUND)

            ip_address = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR'))
            user_agent = request.META.get('HTTP_USER_AGENT', '')

            module_access = ModuleAccess.objects.create(
                user=request.user,
                workspace=workspace,
                module_name=data['module_name'],
                session_duration=data.get('session_duration', 0),
                actions_performed=data.get('actions_performed', []),
                ip_address=ip_address,
                user_agent=user_agent
            )

            return Response({
                'access_record': ModuleAccessSerializer(module_access).data
            }, status=status.HTTP_201_CREATED)

    return await _sync_logic()

@extend_schema(
    tags=["Modules"],
    summary="Workspace Module Analytics",
    description="Get module usage analytics for workspace"
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
@rate_limit(requests_per_minute=50)
async def workspace_module_analytics(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
            return Response({'error': 'Only workspace owners and admins can view module analytics'}, status=status.HTTP_403_FORBIDDEN)

        date_from = request.GET.get('DateFrom')
        date_to = request.GET.get('DateTo')
        module_name = request.GET.get('ModuleName')

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

        module_accesses = ModuleAccess.objects.filter(
            workspace=workspace,
            accessed_at__date__range=[date_from, date_to]
        ).select_related('user')

        if module_name:
            module_accesses = module_accesses.filter(module_name=module_name)

        total_sessions = module_accesses.count()
        unique_users = module_accesses.values('user').distinct().count()
        avg_session_duration = module_accesses.aggregate(avg_duration=Avg('session_duration'))['avg_duration'] or 0

        user_stats = module_accesses.values('user__email', 'user__first_name', 'user__last_name').annotate(
            total_sessions=Count('id'),
            total_duration=Sum('session_duration'),
            last_access=Max('accessed_at')
        ).order_by('-total_sessions')[:5]

        most_active_users = []
        for user_stat in user_stats:
            name = f"{user_stat['user__first_name']} {user_stat['user__last_name']}".strip()
            most_active_users.append({
                'user_email': user_stat['user__email'],
                'user_name': name or user_stat['user__email'],
                'total_sessions': user_stat['total_sessions'],
                'total_duration': user_stat['total_duration'],
                'last_access': user_stat['last_access']
            })

        usage_by_day = []
        current_date = date_from
        while current_date <= date_to:
            day_accesses = module_accesses.filter(accessed_at__date=current_date)
            usage_by_day.append({
                'date': current_date,
                'sessions': day_accesses.count(),
                'unique_users': day_accesses.values('user').distinct().count(),
                'total_duration': day_accesses.aggregate(total=Sum('session_duration'))['total'] or 0
            })
            current_date += timedelta(days=1)

        all_modules = ModuleAccess.objects.filter(
            workspace=workspace,
            accessed_at__date__range=[date_from, date_to]
        ).values('module_name').annotate(
            total_sessions=Count('id'),
            unique_users=Count('user', distinct=True),
            avg_duration=Avg('session_duration')
        ).order_by('-total_sessions')

        popular_modules = []
        total_workspace_sessions = sum(m['total_sessions'] for m in all_modules)

        for module_stat in all_modules:
            popularity_score = (module_stat['total_sessions'] / max(total_workspace_sessions, 1)) * 100
            popular_modules.append({
                'module_name': module_stat['module_name'],
                'total_sessions': module_stat['total_sessions'],
                'unique_users': module_stat['unique_users'],
                'avg_duration': round(module_stat['avg_duration'] or 0, 2),
                'popularity_score': round(popularity_score, 2)
            })

        return Response({
            'module_usage': {
                'total_sessions': total_sessions,
                'unique_users': unique_users,
                'average_session_duration': round(avg_session_duration, 2),
                'most_active_users': most_active_users,
                'usage_by_day': usage_by_day
            },
            'popular_modules': popular_modules
        })

    return await _sync_logic()

@extend_schema(
    tags=["Modules"],
    summary="User Module Preferences",
    description="GET: Get user module preferences. PUT: Update preferences"
)
@api_view(['GET', 'PUT'])
@permission_classes([permissions.IsAuthenticated])
async def user_module_preferences(request, userId):
    @sync_to_async
    def _sync_logic():
        if str(request.user.id) != str(userId):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        preferences, created = ModulePreferences.objects.get_or_create(user=request.user)

        if request.method == 'GET':
            if not preferences.favorite_modules or not preferences.module_order:
                date_from = timezone.now().date() - timedelta(days=30)
                module_accesses = ModuleAccess.objects.filter(
                    user_id=userId,
                    accessed_at__date__gte=date_from
                )

                if module_accesses.exists():
                    top_modules = module_accesses.values('module_name').annotate(
                        count=Count('id')
                    ).order_by('-count')[:3]

                    auto_favorites = [m['module_name'] for m in top_modules]

                    all_modules = ['dashboard', 'tasks', 'team', 'wiki', 'integrations', 'logs', 'reports', 'modules']
                    auto_order = auto_favorites + [m for m in all_modules if m not in auto_favorites]

                    preferences.favorite_modules = auto_favorites
                    preferences.module_order = auto_order
                    preferences.save()

            serializer = ModulePreferencesSerializer(preferences)
            return Response({
                'preferences': serializer.data,
                'auto_generated': created or not preferences.favorite_modules
            })

        elif request.method == 'PUT':
            serializer = ModulePreferencesSerializer(preferences, data=request.data, partial=True)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            serializer.save()
            return Response({'preferences': serializer.data})

    return await _sync_logic()

@extend_schema(
    tags=["Modules"],
    summary="User Module Insights",
    description="Get personalized insights about user's module usage patterns"
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def user_module_insights(request, userId):
    @sync_to_async
    def _sync_logic():
        if str(request.user.id) != str(userId) and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        date_from = timezone.now().date() - timedelta(days=30)
        module_accesses = ModuleAccess.objects.filter(
            user_id=userId,
            accessed_at__date__gte=date_from
        ).select_related('workspace')

        if not module_accesses.exists():
            return Response({
                'message': 'Not enough data yet. Start using BuildTracker to see your insights!',
                'insights': []
            })

        most_used = module_accesses.values('module_name').annotate(
            count=Count('id'),
            total_time=Sum('session_duration')
        ).order_by('-count').first()

        peak_hour = module_accesses.extra(
            select={'hour': 'EXTRACT(hour FROM accessed_at)'}
        ).values('hour').annotate(count=Count('id')).order_by('-count').first()

        all_modules = ['dashboard', 'tasks', 'team', 'wiki', 'integrations', 'logs', 'reports']
        used_modules = set(module_accesses.values_list('module_name', flat=True))
        unused_modules = [m for m in all_modules if m not in used_modules]

        avg_duration = module_accesses.aggregate(avg=Avg('session_duration'))['avg'] or 0

        daily_usage = module_accesses.extra(
            select={'day': 'EXTRACT(dow FROM accessed_at)'}
        ).values('day').annotate(count=Count('id')).order_by('-count').first()

        days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        most_active_day = days[int(daily_usage['day'])] if daily_usage else 'N/A'

        insights = []

        if most_used:
            module_display = dict(ModuleAccess.MODULE_CHOICES).get(most_used['module_name'])
            insights.append({
                'type': 'favorite_module',
                'title': f"You love the {module_display}!",
                'description': f"You've visited {module_display} {most_used['count']} times in the last 30 days.",
                'recommendation': f"We'll show {module_display} first when you log in.",
                'icon': '⭐'
            })

        if peak_hour:
            hour = int(peak_hour['hour'])
            time_period = 'morning' if 6 <= hour < 12 else 'afternoon' if 12 <= hour < 18 else 'evening'
            insights.append({
                'type': 'peak_time',
                'title': f"You're a {time_period} person!",
                'description': f"You're most active around {hour}:00. That's when you get things done!",
                'recommendation': f"Schedule important tasks during your peak {time_period} hours.",
                'icon': '🕐'
            })

        if unused_modules:
            unused_display = ', '.join([dict(ModuleAccess.MODULE_CHOICES).get(m, m) for m in unused_modules[:2]])
            insights.append({
                'type': 'unused_features',
                'title': 'Discover new features!',
                'description': f"You haven't tried {unused_display} yet.",
                'recommendation': f"These features might help your workflow. Give them a try!",
                'icon': '💡'
            })

        if avg_duration > 600:  # More than 10 minutes
            insights.append({
                'type': 'engagement',
                'title': 'You are highly engaged!',
                'description': f"You spend an average of {int(avg_duration/60)} minutes per session.",
                'recommendation': 'Keep up the great work! You are making the most of BuildTracker.',
                'icon': '🚀'
            })
        elif avg_duration < 120:  # Less than 2 minutes
            insights.append({
                'type': 'quick_user',
                'title': 'Quick and efficient!',
                'description': 'You get in, get things done, and get out. Nice!',
                'recommendation': 'Consider using keyboard shortcuts to be even faster.',
                'icon': '⚡'
            })

        insights.append({
            'type': 'daily_pattern',
            'title': f"{most_active_day} is your power day!",
            'description': f"You're most active on {most_active_day}s.",
            'recommendation': f"Plan your important work for {most_active_day}s when you're in the zone.",
            'icon': '📅'
        })

        return Response({
            'summary': {
                'total_sessions': module_accesses.count(),
                'favorite_module': most_used['module_name'] if most_used else None,
                'avg_session_minutes': round(avg_duration / 60, 1),
                'most_active_day': most_active_day,
                'peak_hour': f"{int(peak_hour['hour'])}:00" if peak_hour else None
            },
            'insights': insights
        })
    return await _sync_logic()

