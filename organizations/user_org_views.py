from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.core.cache import cache
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from workspaces.models import Workspace, WorkspaceMember
from files.models import File
from wiki.models import WikiDocumentAttachment
from tasks.models import TaskAttachment, TaskCommentAttachment
# from utils import sanitize_input, rate_limit_key

User = get_user_model()

PLAN_LIMITS = {
    'free': {
        'max_users': 5,
        'max_workspaces': 2,
        'max_storage_mb': 2048  
    },
    'pro': {
        'max_users': 10,
        'max_workspaces': 10,
        'max_storage_mb': 10240
    },
    'business': {
        'max_users': 30,
        'max_workspaces': 30,
        'max_storage_mb': 102400
    },
    'enterprise': {
        'max_users': 999999,
        'max_workspaces': 999999,
        'max_storage_mb': 999999999  
    }
}

def get_plan_limits(plan_type):
    """Get plan limits for a given plan type"""
    return PLAN_LIMITS.get(plan_type, PLAN_LIMITS['free'])

def calculate_user_storage_and_files(user):
    try:
        my_workspaces = Workspace.objects.filter(owner=user)
        
        # Aggregate standard files
        files_data = File.objects.filter(workspace__in=my_workspaces).aggregate(
            count=Count('id'), total_size=Sum('file_size')
        )
        
        # Aggregate Wiki attachments
        wiki_data = WikiDocumentAttachment.objects.filter(
            document__workspace__in=my_workspaces, file__isnull=False
        ).aggregate(count=Count('id'), total_size=Sum('file_size'))
        
        # Aggregate Task and Comment attachments
        task_data = TaskAttachment.objects.filter(
            task__workspace__in=my_workspaces, file__isnull=False
        ).aggregate(count=Count('id'), total_size=Sum('file_size'))
        
        comment_data = TaskCommentAttachment.objects.filter(
            comment__task__workspace__in=my_workspaces, file__isnull=False
        ).aggregate(count=Count('id'), total_size=Sum('file_size'))
        
        total_file_count = (
            (files_data['count'] or 0) +
            (wiki_data['count'] or 0) +
            (task_data['count'] or 0) +
            (comment_data['count'] or 0)
        )
        
        total_storage_bytes = (
            (files_data['total_size'] or 0) +
            (wiki_data['total_size'] or 0) +
            (task_data['total_size'] or 0) +
            (comment_data['total_size'] or 0)
        )
        
        total_storage_mb = total_storage_bytes / (1024 * 1024)
        
        return {
            'file_count': total_file_count,
            'storage_used_mb': round(total_storage_mb, 2),
            'storage_used_bytes': total_storage_bytes
        }
    except Exception as e:
        print(f"Error calculating stats: {e}")
        return {
            'file_count': 0,
            'storage_used_mb': 0.0,
            'storage_used_bytes': 0
        }

def calculate_user_stats(user):
    try:
        my_workspaces = Workspace.objects.filter(owner=user)
        
        try:
            user_count = WorkspaceMember.objects.filter(
                workspace__in=my_workspaces
            ).values('user').distinct().count()
        except Exception:
            user_count = 0
        
        try:
            workspace_count = my_workspaces.count()
        except Exception:
            workspace_count = 0
        
        storage_data = calculate_user_storage_and_files(user)
        
        return {
            'user_count': user_count,
            'workspace_count': workspace_count,
            'storage_used_mb': storage_data['storage_used_mb'],
            'file_count': storage_data['file_count']
        }
    except Exception:
        return {
            'user_count': 0,
            'workspace_count': 0,
            'storage_used_mb': 0.0,
            'file_count': 0
        }

@extend_schema(
    tags=["Organizations"],
    summary="Get User Organization Profile",
    description="GET: Get user profile with aggregated usage from all owned workspaces (User = Organization)",
    responses={
        200: {
            'description': 'User organization profile',
            'content': {
                'application/json': {
                    'example': {
                        'organization': {
                            'id': 'user-uuid',
                            'name': 'John Doe',
                            'email': 'john@example.com',
                            'billing_email': 'billing@example.com',
                            'plan_type': 'pro',
                            'created_at': '2024-01-15T10:00:00Z'
                        },
                        'usage': {
                            'user_count': 15,
                            'workspace_count': 3,
                            'storage_used_mb': 450.5,
                            'file_count': 127
                        },
                        'plan_limits': {
                            'max_users': 50,
                            'max_workspaces': 10,
                            'max_storage_mb': 10240
                        },
                        'member_count': 15
                    }
                }
            }
        },
        401: {'description': 'Authentication required'},
        404: {'description': 'User not found'}
    }
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_user_organization(request, id):
    """
    GET /api/organizations/:id
    Returns user profile + aggregated stats from all owned workspaces
    """
    user = get_object_or_404(User, id=id)
    
    # Only allow users to view their own organization profile
    if user != request.user:
        return Response(
            {'error': 'You can only view your own organization profile'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Calculate usage stats
    usage = calculate_user_stats(user)
    
    # Get plan limits
    limits = get_plan_limits(user.plan_type)
    
    # Build organization response
    full_name = f"{user.first_name} {user.last_name}".strip() or user.email
    
    return Response({
        'organization': {
            'id': str(user.id),
            'name': full_name,
            'email': user.email,
            'billing_email': user.billing_email or user.email,
            'plan_type': user.plan_type,
            'created_at': user.created_at.isoformat()
        },
        'usage': usage,
        'plan_limits': limits,
        'member_count': usage['user_count']
    })

@extend_schema(
    tags=["Organizations"],
    summary="Update User Organization Profile",
    description="PUT: Update user profile (name, billing_email)",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string', 'description': 'Full name'},
                'billing_email': {'type': 'string', 'description': 'Billing email address'}
            }
        }
    },
    responses={
        200: {
            'description': 'Updated organization profile',
            'content': {
                'application/json': {
                    'example': {
                        'organization': {
                            'id': 'user-uuid',
                            'name': 'John Smith',
                            'email': 'john@example.com',
                            'billing_email': 'billing@example.com',
                            'plan_type': 'pro',
                            'created_at': '2024-01-15T10:00:00Z'
                        }
                    }
                }
            }
        },
        400: {'description': 'Invalid input'},
        401: {'description': 'Authentication required'},
        403: {'description': 'Permission denied'}
    }
)
@api_view(['PUT'])
@permission_classes([permissions.IsAuthenticated])
def update_user_organization(request, id):
    """
    PUT /api/organizations/:id
    Updates user profile (name, billing_email)
    """
    user = get_object_or_404(User, id=id)
    
    # Only allow users to update their own profile
    if user != request.user:
        return Response(
            {'error': 'You can only update your own organization profile'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Get and sanitize input
    name = request.data.get('name')
    billing_email = request.data.get('billing_email')
    
    if name:
        from utils import sanitize_input
        name = sanitize_input(name, 100)
        # Split name into first and last name
        name_parts = name.split(' ', 1)
        user.first_name = name_parts[0]
        user.last_name = name_parts[1] if len(name_parts) > 1 else ''
    
    if billing_email:
        from utils import sanitize_input
        billing_email = sanitize_input(billing_email, 254).lower()
        user.billing_email = billing_email
    
    user.save()
    
    full_name = f"{user.first_name} {user.last_name}".strip() or user.email
    
    return Response({
        'organization': {
            'id': str(user.id),
            'name': full_name,
            'email': user.email,
            'billing_email': user.billing_email or user.email,
            'plan_type': user.plan_type,
            'created_at': user.created_at.isoformat()
        }
    })

@extend_schema(
    tags=["Organizations"],
    summary="Delete User Organization",
    description="DELETE: Delete user account and all owned workspaces",
    responses={
        200: {
            'description': 'Organization deleted',
            'content': {
                'application/json': {
                    'example': {
                        'message': 'Organization deleted successfully'
                    }
                }
            }
        },
        401: {'description': 'Authentication required'},
        403: {'description': 'Permission denied'}
    }
)
@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def delete_user_organization(request, id):
    """
    DELETE /api/organizations/:id
    Deletes user account and all owned workspaces
    """
    user = get_object_or_404(User, id=id)
    
    # Only allow users to delete their own account
    if user != request.user:
        return Response(
            {'error': 'You can only delete your own organization'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Delete all workspaces owned by this user (cascade deletes members, tasks, files, etc.)
    Workspace.objects.filter(owner=user).delete()
    
    # Delete the user account
    user.delete()
    
    return Response({'message': 'Organization deleted successfully'})

@extend_schema(
    tags=["Organizations"],
    summary="Get User Organization Usage",
    description="GET: Get detailed usage statistics aggregated from all owned workspaces",
    responses={
        200: {
            'description': 'Usage statistics',
            'content': {
                'application/json': {
                    'example': {
                        'current_usage': {
                            'user_count': 15,
                            'workspace_count': 3,
                            'storage_used_mb': 450.5,
                            'file_count': 127
                        },
                        'limits': {
                            'max_users': 50,
                            'max_workspaces': 10,
                            'max_storage_mb': 10240
                        },
                        'plan_type': 'pro',
                        'usage_percentage': {
                            'users': 30.0,
                            'workspaces': 30.0,
                            'storage': 4.4
                        }
                    }
                }
            }
        },
        401: {'description': 'Authentication required'},
        403: {'description': 'Permission denied'}
    }
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_user_organization_usage(request, id):
    """
    GET /api/organizations/:id/usage
    Returns detailed usage statistics
    """
    user = get_object_or_404(User, id=id)
    
    # Only allow users to view their own usage
    if user != request.user:
        return Response(
            {'error': 'You can only view your own organization usage'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Check cache first
    cache_key = f'user_usage_{user.id}'
    cached_data = cache.get(cache_key)
    
    if cached_data:
        return Response(cached_data)
    
    # Calculate usage stats
    current_usage = calculate_user_stats(user)
    
    # Get plan limits
    limits = get_plan_limits(user.plan_type)
    
    # Calculate usage percentages
    usage_percentage = {
        'users': round((current_usage['user_count'] / limits['max_users']) * 100, 2) if limits['max_users'] > 0 else 0,
        'workspaces': round((current_usage['workspace_count'] / limits['max_workspaces']) * 100, 2) if limits['max_workspaces'] > 0 else 0,
        'storage': round((current_usage['storage_used_mb'] / limits['max_storage_mb']) * 100, 2) if limits['max_storage_mb'] > 0 else 0,
    }
    
    response_data = {
        'current_usage': current_usage,
        'limits': limits,
        'plan_type': user.plan_type,
        'usage_percentage': usage_percentage
    }
    
    # Cache for 5 minutes
    cache.set(cache_key, response_data, 300)
    
    return Response(response_data)

@extend_schema(
    tags=["Organizations"],
    summary="Calculate User Organization Usage",
    description="POST: Force recalculation of usage statistics (clears cache)",
    responses={
        200: {
            'description': 'Usage calculated',
            'content': {
                'application/json': {
                    'example': {
                        'usage': {
                            'user_count': 15,
                            'workspace_count': 3,
                            'storage_used_mb': 450.5,
                            'file_count': 127
                        },
                        'calculated_at': '2024-01-20T14:30:00Z'
                    }
                }
            }
        },
        401: {'description': 'Authentication required'},
        403: {'description': 'Permission denied'},
        429: {'description': 'Rate limit exceeded'}
    }
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def calculate_user_organization_usage(request, id):
    """
    POST /api/organizations/:id/usage/calculate
    Forces fresh calculation of usage stats
    """
    user = get_object_or_404(User, id=id)
    
    # Only allow users to calculate their own usage
    if user != request.user:
        return Response(
            {'error': 'You can only calculate your own organization usage'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Rate limiting
    from utils import rate_limit_key
    rate_key = rate_limit_key(user.id, 'calculate_usage')
    if cache.get(rate_key):
        return Response(
            {'error': 'Rate limit exceeded. Please wait before calculating again.'}, 
            status=status.HTTP_429_TOO_MANY_REQUESTS
        )
    
    cache.set(rate_key, True, 60)  # 1 minute rate limit
    
    # Calculate fresh stats
    usage = calculate_user_stats(user)
    
    # Clear cache
    cache_key = f'user_usage_{user.id}'
    cache.delete(cache_key)
    
    calculated_at = timezone.now()
    
    return Response({
        'usage': usage,
        'calculated_at': calculated_at.isoformat()
    })

@extend_schema(
    tags=["Organizations"],
    summary="Check User Organization Limits",
    description="GET: Check if user can perform actions based on plan limits",
    responses={
        200: {
            'description': 'Limits check result',
            'content': {
                'application/json': {
                    'example': {
                        'can_add_user': True,
                        'can_create_workspace': True,
                        'can_upload_file': True,
                        'storage_available_mb': 9789.5,
                        'limits_exceeded': []
                    }
                }
            }
        },
        401: {'description': 'Authentication required'},
        403: {'description': 'Permission denied'}
    }
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def check_user_organization_limits(request, id):
    """
    GET /api/organizations/:id/limits/check
    Checks if user can perform actions based on current usage vs plan limits
    """
    user = get_object_or_404(User, id=id)
    
    # Only allow users to check their own limits
    if user != request.user:
        return Response(
            {'error': 'You can only check your own organization limits'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Get current usage
    current_usage = calculate_user_stats(user)
    
    # Get plan limits
    limits = get_plan_limits(user.plan_type)
    
    # Check what's allowed
    can_add_user = current_usage['user_count'] < limits['max_users']
    can_create_workspace = current_usage['workspace_count'] < limits['max_workspaces']
    can_upload_file = current_usage['storage_used_mb'] < limits['max_storage_mb']
    
    # Calculate available storage
    storage_available_mb = max(0, limits['max_storage_mb'] - current_usage['storage_used_mb'])
    
    # List exceeded limits
    limits_exceeded = []
    if not can_add_user:
        limits_exceeded.append('max_users')
    if not can_create_workspace:
        limits_exceeded.append('max_workspaces')
    if not can_upload_file:
        limits_exceeded.append('max_storage')
    
    return Response({
        'can_add_user': can_add_user,
        'can_create_workspace': can_create_workspace,
        'can_upload_file': can_upload_file,
        'storage_available_mb': round(storage_available_mb, 2),
        'limits_exceeded': limits_exceeded
    })
