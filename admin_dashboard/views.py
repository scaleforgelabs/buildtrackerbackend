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


@extend_schema(
    tags=["Admin Dashboard"],
    summary="Admin Dashboard Stats",
    description="Returns platform-wide stats. Accessible to admins and super admins.",
    responses={
        200: {
            'type': 'object',
            'properties': {
                'total_users': {'type': 'integer'},
                'active_users': {'type': 'integer'},
                'new_users_this_week': {'type': 'integer'},
                'admins': {'type': 'integer'},
                'super_admins': {'type': 'integer'},
            }
        },
        403: {'description': 'Forbidden — requires admin or super_admin platform role'}
    }
)
@api_view(['GET'])
@permission_classes([IsAdmin])
async def admin_stats_view(request):
    @sync_to_async
    def _sync_logic():
        now = timezone.now()
        week_ago = now - timedelta(days=7)

        total_users = User.objects.count()
        active_users = User.objects.filter(status='active').count()
        new_users_this_week = User.objects.filter(created_at__gte=week_ago).count()
        admins = User.objects.filter(platform_role='admin').count()
        super_admins = User.objects.filter(platform_role='super_admin').count()

        return Response({
            'total_users': total_users,
            'active_users': active_users,
            'new_users_this_week': new_users_this_week,
            'admins': admins,
            'super_admins': super_admins,
        })

    return await _sync_logic()


@extend_schema(
    tags=["Admin Dashboard"],
    summary="List All Users (Admin)",
    description="Paginated list of all platform users. Accessible to admins and super admins.",
    responses={
        200: {
            'type': 'object',
            'properties': {
                'users': {'type': 'array', 'items': {'type': 'object'}},
                'total': {'type': 'integer'},
            }
        },
        403: {'description': 'Forbidden — requires admin or super_admin platform role'}
    }
)
@api_view(['GET'])
@permission_classes([IsAdmin])
async def admin_users_view(request):
    @sync_to_async
    def _sync_logic():
        page = int(request.query_params.get('page', 1))
        page_size = 20
        offset = (page - 1) * page_size

        qs = User.objects.order_by('-created_at')[offset:offset + page_size]
        total = User.objects.count()

        users = [
            {
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
            for u in qs
        ]

        return Response({'users': users, 'total': total, 'page': page, 'page_size': page_size})

    return await _sync_logic()


@extend_schema(
    tags=["Admin Dashboard"],
    summary="Update User Platform Role (Super Admin only)",
    description="Change a user's platform_role. Accessible to super admins only.",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'platform_role': {
                    'type': 'string',
                    'enum': ['user', 'admin', 'super_admin'],
                }
            },
            'required': ['platform_role']
        }
    },
    responses={
        200: {'description': 'Role updated successfully'},
        400: {'description': 'Invalid role'},
        403: {'description': 'Forbidden — requires super_admin platform role'},
        404: {'description': 'User not found'},
    }
)
@api_view(['PATCH'])
@permission_classes([IsSuperAdmin])
async def admin_update_user_role_view(request, user_id):
    @sync_to_async
    def _sync_logic():
        new_role = request.data.get('platform_role')
        valid_roles = ('user', 'admin', 'super_admin')

        if new_role not in valid_roles:
            return Response(
                {'error': f'Invalid role. Must be one of: {", ".join(valid_roles)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        target_user.platform_role = new_role
        target_user.save(update_fields=['platform_role'])

        return Response({
            'id': str(target_user.id),
            'email': target_user.email,
            'platform_role': target_user.platform_role,
        })

    return await _sync_logic()
