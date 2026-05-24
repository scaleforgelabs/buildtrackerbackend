from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework.decorators import permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from drf_spectacular.utils import extend_schema
from permissions import IsAdmin, IsSuperAdmin

User = get_user_model()


# ─── helpers ────────────────────────────────────────────────────────────────

def _user_row(u):
    return {
        'id': str(u.id),
        'email': u.email,
        'first_name': u.first_name,
        'last_name': u.last_name,
        'platform_role': u.platform_role,
        'plan_type': u.plan_type,
        'status': u.status,
        'is_verified': u.is_verified,
        'created_at': u.created_at.isoformat(),
    }


# ─── stats ───────────────────────────────────────────────────────────────────

@extend_schema(tags=["Admin Dashboard"], summary="Platform Stats")
@api_view(['GET'])
@permission_classes([IsAdmin])
async def admin_stats_view(request):
    @sync_to_async
    def _sync():
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        return Response({
            'total_users': User.objects.count(),
            'active_users': User.objects.filter(status='active').count(),
            'new_users_this_week': User.objects.filter(created_at__gte=week_ago).count(),
            'admins': User.objects.filter(platform_role='admin').count(),
            'super_admins': User.objects.filter(platform_role='super_admin').count(),
        })
    return await _sync()


# ─── users ───────────────────────────────────────────────────────────────────

@extend_schema(tags=["Admin Dashboard"], summary="List Users")
@api_view(['GET'])
@permission_classes([IsAdmin])
async def admin_users_view(request):
    @sync_to_async
    def _sync():
        from django.db.models import Q
        page = int(request.query_params.get('page', 1))
        page_size = 20
        offset = (page - 1) * page_size
        search = request.query_params.get('search', '').strip()
        unverified_only = request.query_params.get('unverified', '').lower() == 'true'

        qs = User.objects.all()
        if search:
            qs = qs.filter(
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )
        if unverified_only:
            qs = qs.filter(is_verified=False)

        qs = qs.order_by('-created_at')
        total = qs.count()
        users = [_user_row(u) for u in qs[offset:offset + page_size]]
        return Response({'users': users, 'total': total, 'page': page, 'page_size': page_size})
    return await _sync()


@extend_schema(tags=["Admin Dashboard"], summary="Update User Platform Role")
@api_view(['PATCH'])
@permission_classes([IsSuperAdmin])
async def admin_update_user_role_view(request, user_id):
    @sync_to_async
    def _sync():
        new_role = request.data.get('platform_role')
        valid_roles = ('user', 'admin', 'super_admin')
        if new_role not in valid_roles:
            return Response({'error': f'Invalid role'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            target = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        target.platform_role = new_role
        target.save(update_fields=['platform_role'])
        return Response({'id': str(target.id), 'email': target.email, 'platform_role': target.platform_role})
    return await _sync()


@extend_schema(tags=["Admin Dashboard"], summary="Delete User")
@api_view(['DELETE'])
@permission_classes([IsAdmin])
async def admin_delete_user_view(request, user_id):
    @sync_to_async
    def _sync():
        try:
            target = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        if str(target.id) == str(request.user.id):
            return Response({'error': 'Cannot delete your own account'}, status=status.HTTP_403_FORBIDDEN)
        if request.user.platform_role == 'admin' and target.is_verified:
            return Response({'error': 'Admins can only delete unverified users'}, status=status.HTTP_403_FORBIDDEN)
        if request.user.platform_role == 'super_admin' and target.platform_role == 'super_admin':
            return Response({'error': 'Cannot delete another super admin'}, status=status.HTTP_403_FORBIDDEN)
        email = target.email
        target.delete()
        return Response({'message': f'User {email} deleted'})
    return await _sync()


@extend_schema(tags=["Admin Dashboard"], summary="Suspend / Unsuspend User")
@api_view(['PATCH'])
@permission_classes([IsAdmin])
async def admin_suspend_user_view(request, user_id):
    @sync_to_async
    def _sync():
        action = request.data.get('action')
        if action not in ('suspend', 'unsuspend'):
            return Response({'error': 'action must be suspend or unsuspend'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            target = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        if str(target.id) == str(request.user.id):
            return Response({'error': 'Cannot suspend your own account'}, status=status.HTTP_403_FORBIDDEN)
        if request.user.platform_role == 'admin' and target.platform_role in ('admin', 'super_admin'):
            return Response({'error': 'Admins cannot suspend other admins'}, status=status.HTTP_403_FORBIDDEN)
        if request.user.platform_role == 'super_admin' and target.platform_role == 'super_admin':
            return Response({'error': 'Cannot suspend another super admin'}, status=status.HTTP_403_FORBIDDEN)
        target.status = 'inactive' if action == 'suspend' else 'active'
        target.save(update_fields=['status'])
        return Response({'id': str(target.id), 'email': target.email, 'status': target.status})
    return await _sync()


# ─── workspaces ──────────────────────────────────────────────────────────────

@extend_schema(tags=["Admin Dashboard"], summary="List All Workspaces")
@api_view(['GET'])
@permission_classes([IsAdmin])
async def admin_workspaces_view(request):
    @sync_to_async
    def _sync():
        from django.db.models import Count, Q
        from workspaces.models import Workspace
        page = int(request.query_params.get('page', 1))
        page_size = 20
        offset = (page - 1) * page_size
        search = request.query_params.get('search', '').strip()
        ws_type = request.query_params.get('type', '').strip()
        ws_status = request.query_params.get('status', '').strip()

        qs = Workspace.objects.select_related('owner').annotate(
            member_count=Count('members', distinct=True),
            task_count=Count('tasks', distinct=True),
        )
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(owner__email__icontains=search))
        if ws_type:
            qs = qs.filter(type=ws_type)
        if ws_status:
            qs = qs.filter(status=ws_status)

        total = qs.count()
        rows = []
        for ws in qs.order_by('-created_at')[offset:offset + page_size]:
            rows.append({
                'id': str(ws.id),
                'name': ws.name,
                'slug': ws.slug,
                'type': ws.type,
                'status': ws.status,
                'owner_email': ws.owner.email,
                'owner_name': f'{ws.owner.first_name} {ws.owner.last_name}'.strip(),
                'member_count': ws.member_count,
                'task_count': ws.task_count,
                'created_at': ws.created_at.isoformat(),
            })
        return Response({'workspaces': rows, 'total': total, 'page': page, 'page_size': page_size})
    return await _sync()


# ─── analytics ───────────────────────────────────────────────────────────────

@extend_schema(tags=["Admin Dashboard"], summary="Platform Analytics")
@api_view(['GET'])
@permission_classes([IsAdmin])
async def admin_analytics_view(request):
    @sync_to_async
    def _sync():
        from django.db.models import Count
        from django.db.models.functions import TruncDate, TruncMonth
        from workspaces.models import Workspace, WorkspaceSettings

        now = timezone.now()
        days = int(request.query_params.get('days', 30))
        since = now - timedelta(days=days)

        # User growth (daily signups)
        user_growth = list(
            User.objects.filter(created_at__gte=since)
            .annotate(date=TruncDate('created_at'))
            .values('date')
            .annotate(count=Count('id'))
            .order_by('date')
            .values('date', 'count')
        )
        for row in user_growth:
            row['date'] = row['date'].isoformat()

        # Workspace growth (daily)
        ws_growth = list(
            Workspace.objects.filter(created_at__gte=since)
            .annotate(date=TruncDate('created_at'))
            .values('date')
            .annotate(count=Count('id'))
            .order_by('date')
            .values('date', 'count')
        )
        for row in ws_growth:
            row['date'] = row['date'].isoformat()

        # Workspace types breakdown
        ws_types = list(
            Workspace.objects.values('type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # Most used modules (from WorkspaceSettings.enabled_modules JSON)
        module_counts = {}
        for s in WorkspaceSettings.objects.all():
            mods = s.enabled_modules or {}
            for mod, enabled in mods.items():
                if enabled:
                    module_counts[mod] = module_counts.get(mod, 0) + 1

        most_used_modules = sorted(
            [{'module': k, 'count': v} for k, v in module_counts.items()],
            key=lambda x: -x['count']
        )

        # Plan distribution
        plan_dist = list(
            User.objects.values('plan_type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # Top workspaces by task count
        from django.db.models import Count as C
        top_workspaces = list(
            Workspace.objects.annotate(task_count=C('tasks', distinct=True))
            .order_by('-task_count')[:10]
            .values('name', 'type', 'task_count', 'slug')
        )

        return Response({
            'user_growth': user_growth,
            'workspace_growth': ws_growth,
            'workspace_types': ws_types,
            'most_used_modules': most_used_modules,
            'plan_distribution': plan_dist,
            'top_workspaces': top_workspaces,
            'days': days,
        })
    return await _sync()


# ─── subscriptions ───────────────────────────────────────────────────────────

@extend_schema(tags=["Admin Dashboard"], summary="Subscriptions Overview")
@api_view(['GET'])
@permission_classes([IsAdmin])
async def admin_subscriptions_view(request):
    @sync_to_async
    def _sync():
        from django.db.models import Count
        from subscriptions.models import Subscription, PaymentHistory

        page = int(request.query_params.get('page', 1))
        page_size = 20
        offset = (page - 1) * page_size
        search = request.query_params.get('search', '').strip()

        # Plan breakdown
        plan_breakdown = list(
            Subscription.objects.values('plan_type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        status_breakdown = list(
            Subscription.objects.values('status')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # Total paid (active non-free)
        paid_count = Subscription.objects.filter(status='active').exclude(plan_type='free').count()
        free_count = Subscription.objects.filter(plan_type='free').count()
        total = Subscription.objects.count()

        qs = Subscription.objects.select_related('organization')
        if search:
            qs = qs.filter(organization__name__icontains=search)

        rows = []
        for sub in qs.order_by('-created_at')[offset:offset + page_size]:
            rows.append({
                'id': str(sub.id),
                'organization': sub.organization.name if sub.organization else '—',
                'plan_type': sub.plan_type,
                'billing_cycle': sub.billing_cycle,
                'status': sub.status,
                'payment_provider': sub.payment_provider or '—',
                'start_date': sub.start_date.isoformat(),
                'end_date': sub.end_date.isoformat() if sub.end_date else None,
                'cancel_at_period_end': sub.cancel_at_period_end,
            })

        return Response({
            'subscriptions': rows,
            'total': total,
            'paid_count': paid_count,
            'free_count': free_count,
            'plan_breakdown': plan_breakdown,
            'status_breakdown': status_breakdown,
            'page': page,
            'page_size': page_size,
        })
    return await _sync()


# ─── newsletter ───────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Admin Dashboard"],
    summary="Send Newsletter / Broadcast Email",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'subject': {'type': 'string'},
                'message': {'type': 'string'},
                'audience': {'type': 'string', 'enum': ['all', 'pro', 'free', 'enterprise', 'verified', 'unverified']},
                'action_url': {'type': 'string'},
                'action_text': {'type': 'string'},
            },
            'required': ['subject', 'message']
        }
    },
    responses={200: {'description': 'Queued successfully'}, 403: {'description': 'Forbidden'}}
)
@api_view(['POST'])
@permission_classes([IsAdmin])
async def admin_newsletter_view(request):
    @sync_to_async
    def _sync():
        from core.tasks import send_email_task

        subject = request.data.get('subject', '').strip()
        message = request.data.get('message', '').strip()
        audience = request.data.get('audience', 'all')
        action_url = request.data.get('action_url', '').strip()
        action_text = request.data.get('action_text', 'Open BuildTracker').strip()

        if not subject or not message:
            return Response({'error': 'subject and message are required'}, status=status.HTTP_400_BAD_REQUEST)

        qs = User.objects.filter(status='active', is_verified=True)
        if audience == 'pro':
            qs = qs.filter(plan_type='pro')
        elif audience == 'free':
            qs = qs.filter(plan_type='free')
        elif audience == 'enterprise':
            qs = qs.filter(plan_type='enterprise')
        elif audience == 'unverified':
            qs = User.objects.filter(is_verified=False)

        emails = list(qs.values_list('email', flat=True))
        if not emails:
            return Response({'error': 'No recipients found for this audience'}, status=status.HTTP_400_BAD_REQUEST)

        extra_context = {
            'email_type': 'general_update',
            'chip_label': 'BuildTracker Update',
            'action_url': action_url or None,
            'action_text': action_text,
        }

        # Send in batches of 50 via Celery
        batch_size = 50
        queued = 0
        for i in range(0, len(emails), batch_size):
            batch = emails[i:i + batch_size]
            send_email_task.delay(
                subject=subject,
                message=message,
                recipient_list=batch,
                fail_silently=True,
                extra_context=extra_context,
            )
            queued += len(batch)

        return Response({
            'message': f'Newsletter queued for {queued} recipients',
            'recipient_count': queued,
            'audience': audience,
        })
    return await _sync()
