from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework import status, permissions
from rest_framework.decorators import permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta
from drf_spectacular.utils import extend_schema
import secrets
import string
from .models import Organization, OrganizationMembership, OrganizationUsage, OrganizationInvitation
from .serializers import (
    OrganizationSerializer, OrganizationCreateSerializer, OrganizationUpdateSerializer,
    OrganizationUsageSerializer, PlanSerializer, UsageCheckSerializer, UsageDetailSerializer
)
from .tasks import calculate_organization_usage, send_organization_invitation_email
from utils import sanitize_input, IsOrganizationOwner, IsOrganizationMember, rate_limit_key

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'PageSize'
    max_page_size = 100
    page_query_param = 'Page'

def get_filtered_queryset(queryset, request):
    search_key = request.GET.get('SearchKey')
    date_from = request.GET.get('DateFrom')
    date_to = request.GET.get('DateTo')
    sort_column = request.GET.get('SortColumn', 'created_at')
    sort_order = request.GET.get('SortOrder', 'desc')
    
    if search_key:
        search_key = sanitize_input(search_key)
        queryset = queryset.filter(
            Q(name__icontains=search_key) | 
            Q(billing_email__icontains=search_key)
        )
    
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)
    
    order_prefix = '-' if sort_order == 'desc' else ''
    queryset = queryset.order_by(f"{order_prefix}{sort_column}")
    
    return queryset

@extend_schema(
    tags=["Organizations"],
    summary="Get Organization",
    description="Get organization details with usage and plan limits",
    responses={
        200: {
            'type': 'object',
            'properties': {
                'id': {'type': 'string'},
                'name': {'type': 'string'},
                'usage': {'type': 'object'},
                'plan_limits': {'type': 'object'},
                'member_count': {'type': 'integer'}
            }
        },
        403: {'description': 'Permission denied'},
        404: {'description': 'Organization not found'}
    }
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def get_organization(request, id):
    @sync_to_async
    def _sync_logic():
        organization = get_object_or_404(Organization, id=id)

        if not (organization.owner == request.user or 
                organization.members.filter(id=request.user.id).exists()):
            return Response(
                {'error': 'Permission denied'}, 
                status=status.HTTP_403_FORBIDDEN
            )

        usage = organization.get_current_usage()
        plan_limits = organization.get_plan_limits()

        serializer = OrganizationSerializer(organization)
        data = serializer.data
        data['usage'] = usage
        data['plan_limits'] = plan_limits
        data['member_count'] = organization.member_count

        return Response(data)

    return await _sync_logic()

@extend_schema(
    tags=["Organizations"],
    summary="Update Organization",
    description="Update organization details (owner only)",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string', 'description': 'Organization name'},
                'billing_email': {'type': 'string', 'description': 'Billing email'},
                'plan_type': {'type': 'string', 'description': 'Plan type'}
            }
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string', 'description': 'Organization name'},
                'billing_email': {'type': 'string', 'description': 'Billing email'},
                'plan_type': {'type': 'string', 'description': 'Plan type'}
            }
        }
    },
    responses={
        200: {
            'type': 'object',
            'properties': {
                'organization': {'type': 'object'}
            }
        },
        400: {'description': 'Invalid input'},
        403: {'description': 'Only organization owner can update'},
        404: {'description': 'Organization not found'}
    }
)
@api_view(['PUT'])
@permission_classes([permissions.IsAuthenticated])
async def update_organization(request, id):
    @sync_to_async
    def _sync_logic():
        organization = get_object_or_404(Organization, id=id)

        if organization.owner != request.user:
            return Response(
                {'error': 'Only organization owner can update organization'}, 
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = OrganizationUpdateSerializer(
            organization, 
            data=request.data, 
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response({'organization': OrganizationSerializer(organization).data})

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    return await _sync_logic()

@extend_schema(
    tags=["Organizations"],
    summary="Delete Organization",
    description="Delete organization (owner only)",
    responses={
        200: {
            'type': 'object',
            'properties': {
                'message': {'type': 'string'}
            }
        },
        403: {'description': 'Only organization owner can delete'},
        404: {'description': 'Organization not found'}
    }
)
@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
async def delete_organization(request, id):
    @sync_to_async
    def _sync_logic():
        organization = get_object_or_404(Organization, id=id)

        if organization.owner != request.user:
            return Response(
                {'error': 'Only organization owner can delete organization'}, 
                status=status.HTTP_403_FORBIDDEN
            )

        organization.delete()
        return Response({'message': 'Organization deleted successfully'})

    return await _sync_logic()

@extend_schema(
    tags=["Organizations"],
    summary="Get Organization Usage",
    description="Get current organization usage statistics and limits",
    responses={
        200: {
            'type': 'object',
            'properties': {
                'current_usage': {'type': 'object'},
                'limits': {'type': 'object'},
                'plan_type': {'type': 'string'},
                'usage_percentage': {'type': 'object'}
            }
        },
        403: {'description': 'Permission denied'},
        404: {'description': 'Organization not found'}
    }
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def get_organization_usage(request, id):
    @sync_to_async
    def _sync_logic():
        organization = get_object_or_404(Organization, id=id)

        if not (organization.owner == request.user or 
                organization.members.filter(id=request.user.id).exists()):
            return Response(
                {'error': 'Permission denied'}, 
                status=status.HTTP_403_FORBIDDEN
            )

        current_usage = organization.get_current_usage()
        limits = organization.get_plan_limits()

        usage_percentage = {
            'users': (current_usage['user_count'] / limits['max_users']) * 100 if limits['max_users'] > 0 else 0,
            'workspaces': (current_usage['workspace_count'] / limits['max_workspaces']) * 100 if limits['max_workspaces'] > 0 else 0,
            'storage': (current_usage['storage_used_mb'] / limits['max_storage_mb']) * 100 if limits['max_storage_mb'] > 0 else 0,
        }

        return Response({
            'current_usage': current_usage,
            'limits': limits,
            'plan_type': organization.plan_type,
            'usage_percentage': usage_percentage
        })

    return await _sync_logic()

@extend_schema(
    tags=["Organizations"],
    summary="Calculate Organization Usage",
    description="Trigger calculation of organization usage statistics",
    responses={
        200: {
            'type': 'object',
            'properties': {
                'usage': {'type': 'object'},
                'calculated_at': {'type': 'string'}
            }
        },
        403: {'description': 'Permission denied'},
        404: {'description': 'Organization not found'},
        429: {'description': 'Rate limit exceeded'}
    }
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
async def calculate_usage(request, id):
    @sync_to_async
    def _sync_logic():
        organization = get_object_or_404(Organization, id=id)

        if not (organization.owner == request.user or 
                organization.members.filter(id=request.user.id).exists()):
            return Response(
                {'error': 'Permission denied'}, 
                status=status.HTTP_403_FORBIDDEN
            )

        rate_key = rate_limit_key(request.user.id, 'calculate_usage')
        if cache.get(rate_key):
            return Response(
                {'error': 'Rate limit exceeded. Please wait before calculating again.'}, 
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        cache.set(rate_key, True, 60)

        calculate_organization_usage.delay(str(organization.id))

        usage, created = OrganizationUsage.objects.get_or_create(
            organization=organization,
            defaults={
                'user_count': organization.member_count,
                'workspace_count': 0,
                'storage_used_mb': 0,
                'file_count': 0
            }
        )

        usage.user_count = organization.member_count
        usage.save()

        return Response({
            'usage': OrganizationUsageSerializer(usage).data,
            'calculated_at': timezone.now().isoformat()
        })

    return await _sync_logic()

@extend_schema(
    tags=["Organizations"],
    summary="Check Organization Limits",
    description="Check organization limits and available resources",
    responses={
        200: {
            'type': 'object',
            'properties': {
                'can_add_user': {'type': 'boolean'},
                'can_create_workspace': {'type': 'boolean'},
                'can_upload_file': {'type': 'boolean'},
                'storage_available_mb': {'type': 'integer'},
                'limits_exceeded': {'type': 'array', 'items': {'type': 'string'}}
            }
        },
        403: {'description': 'Permission denied'},
        404: {'description': 'Organization not found'}
    }
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def check_limits(request, id):
    @sync_to_async
    def _sync_logic():
        organization = get_object_or_404(Organization, id=id)

        if not (organization.owner == request.user or 
                organization.members.filter(id=request.user.id).exists()):
            return Response(
                {'error': 'Permission denied'}, 
                status=status.HTTP_403_FORBIDDEN
            )

        current_usage = organization.get_current_usage()
        limits = organization.get_plan_limits()

        can_add_user = organization.can_add_user()
        can_create_workspace = organization.can_create_workspace()
        can_upload_file = organization.can_upload_file()

        storage_available_mb = max(0, limits['max_storage_mb'] - current_usage['storage_used_mb'])

        limits_exceeded = []
        if current_usage['user_count'] >= limits['max_users']:
            limits_exceeded.append('users')
        if current_usage['workspace_count'] >= limits['max_workspaces']:
            limits_exceeded.append('workspaces')
        if current_usage['storage_used_mb'] >= limits['max_storage_mb']:
            limits_exceeded.append('storage')

        return Response({
            'can_add_user': can_add_user,
            'can_create_workspace': can_create_workspace,
            'can_upload_file': can_upload_file,
            'storage_available_mb': storage_available_mb,
            'limits_exceeded': limits_exceeded
        })



    return await _sync_logic()

@extend_schema(
    tags=["Organizations"],
    summary="Get Available Plans",
    description="Get list of available organization plans with pricing and features",
    responses={
        200: {
            'type': 'object',
            'properties': {
                'plans': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'type': {'type': 'string'},
                            'name': {'type': 'string'},
                            'price_naira': {'type': 'integer'},
                            'price_usd': {'type': 'integer'},
                            'limits': {'type': 'object'},
                            'features': {'type': 'array', 'items': {'type': 'string'}}
                        }
                    }
                }
            }
        }
    }
)
@api_view(['GET'])
async def get_plans(request):
    @sync_to_async
    def _sync_logic():
        plans = [
            {
                'type': 'free',
                'name': 'Starter Organization',
                'price_naira': 0,
                'price_usd': 0,
                'limits': {
                    'max_users': 5,
                    'max_workspaces': 2,
                    'max_storage_mb': 2048
                },
                'features': [
                    'Up to 5 users',
                    'Up to 2 workspaces',
                    '2GB storage',
                    'Basic support'
                ]
            },
            {
                'type': 'pro',
                'name': 'Pro Organization',
                'price_naira': 6000,
                'price_usd': 6,
                'limits': {
                    'max_users': 10,
                    'max_workspaces': 10,
                    'max_storage_mb': 10240
                },
                'features': [
                    'Up to 10 users',
                    'Up to 10 workspaces',
                    '10GB storage',
                    'Priority support',
                    'Advanced analytics'
                ]
            },
            {
                'type': 'business',
                'name': 'Business Organization',
                'price_naira': 18000,
                'price_usd': 18,
                'limits': {
                    'max_users': 30,
                    'max_workspaces': 30,
                    'max_storage_mb': 102400
                },
                'features': [
                    'Up to 30 users',
                    'Up to 30 workspaces',
                    '100GB storage',
                    '24/7 support',
                    'Advanced analytics',
                    'Custom integrations',
                    'SSO support'
                ]
            }
        ]

        return Response({'plans': plans})

    return await _sync_logic()

@extend_schema(
    tags=["Organizations"],
    summary="Send Organization Invitation",
    description="Send invitation to join organization",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'email': {'type': 'string', 'description': 'Invitee email address'},
                'role': {'type': 'string', 'enum': ['admin', 'member'], 'description': 'Role in organization'}
            },
            'required': ['email', 'role']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'email': {'type': 'string', 'description': 'Invitee email address'},
                'role': {'type': 'string', 'enum': ['admin', 'member'], 'description': 'Role in organization'}
            },
            'required': ['email', 'role']
        }
    },
    responses={
        201: {
            'type': 'object',
            'properties': {
                'invitation': {'type': 'object'},
                'message': {'type': 'string'}
            }
        },
        400: {'description': 'Invalid input or user limit exceeded'},
        403: {'description': 'Only organization owners can send invitations'}
    }
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
async def send_organization_invitation(request, id):
    @sync_to_async
    def _sync_logic():
        organization = get_object_or_404(Organization, id=id)

        if organization.owner != request.user:
            return Response(
                {'error': 'Only organization owner can send invitations'}, 
                status=status.HTTP_403_FORBIDDEN
            )

        email = sanitize_input(request.data.get('email', ''), 254).lower()
        role = request.data.get('role', 'member')

        if not email:
            return Response({'error': 'Email required'}, status=status.HTTP_400_BAD_REQUEST)

        if role not in ['admin', 'member']:
            return Response({'error': 'Invalid role'}, status=status.HTTP_400_BAD_REQUEST)

        if not organization.can_add_user():
            return Response(
                {'error': 'User limit exceeded for organization plan'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        if OrganizationInvitation.objects.filter(organization=organization, email=email, status='pending').exists():
            return Response({'error': 'Invitation already sent to this email'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
            invitation = OrganizationInvitation.objects.create(
                organization=organization,
                email=email,
                invited_by=request.user,
                role=role,
                token=token,
                expires_at=timezone.now() + timedelta(days=7)
            )

            send_organization_invitation_email.delay(str(invitation.id))

            # Also send email directly as fallback
            from core.tasks import send_email_task
            from django.conf import settings

            try:
                invitation_url = f"{settings.FRONTEND_URL}/invitations/{invitation.token}"
                send_email_task.delay(
                    subject=f'Invitation to join {organization.name}',
                    message=f'You have been invited to join {organization.name} as a {role}. Click the link to accept: {invitation_url}',
                    recipient_list=[email],
                    fail_silently=False,
                )
            except Exception as mail_error:
                print(f"Direct email failed: {mail_error}")

            return Response({
                'invitation': {
                    'id': str(invitation.id),
                    'email': invitation.email,
                    'role': invitation.role,
                    'status': invitation.status,
                    'expires_at': invitation.expires_at
                },
                'message': 'Invitation sent successfully'
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({'error': f'Failed to send invitation: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return await _sync_logic()

@extend_schema(
    tags=["Organizations"],
    summary="Accept Organization Invitation",
    description="Accept an organization invitation using token",
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
                'organization': {'type': 'object'},
                'message': {'type': 'string'}
            }
        },
        400: {'description': 'Invalid or expired invitation token'},
        401: {'description': 'Authentication required'}
    }
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
async def accept_organization_invitation(request):
    @sync_to_async
    def _sync_logic():
        from django.db import transaction

        token = request.data.get('token')

        if not token:
            return Response({'error': 'Invitation token required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            invitation = OrganizationInvitation.objects.get(token=token)

            if not invitation.is_valid():
                return Response({'error': 'Invalid or expired invitation'}, status=status.HTTP_400_BAD_REQUEST)

            if invitation.email.lower() != request.user.email.lower():
                return Response({'error': 'This invitation is not for your email address'}, status=status.HTTP_400_BAD_REQUEST)

            if OrganizationMembership.objects.filter(organization=invitation.organization, user=request.user).exists():
                return Response({'error': 'You are already a member of this organization'}, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                OrganizationMembership.objects.create(
                    organization=invitation.organization,
                    user=request.user,
                    role=invitation.role
                )

                invitation.status = 'accepted'
                invitation.save()

                usage, _ = OrganizationUsage.objects.get_or_create(
                    organization=invitation.organization,
                    defaults={'user_count': 1}
                )
                usage.user_count = invitation.organization.member_count
                usage.save()

            return Response({
                'organization': OrganizationSerializer(invitation.organization).data,
                'message': 'Successfully joined organization'
            })

        except OrganizationInvitation.DoesNotExist:
            return Response({'error': 'Invalid invitation token'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': f'Failed to accept invitation: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return await _sync_logic()

@extend_schema(
    tags=["Organizations"],
    summary="Get My Organizations",
    description="Get all organizations that the authenticated user belongs to with their roles",
    responses={
        200: {
            'type': 'object',
            'properties': {
                'organizations': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'id': {'type': 'string'},
                            'name': {'type': 'string'},
                            'role': {'type': 'string'},
                            'is_owner': {'type': 'boolean'},
                            'member_count': {'type': 'integer'},
                            'plan_type': {'type': 'string'},
                            'joined_at': {'type': 'string'}
                        }
                    }
                }
            }
        },
        401: {'description': 'Authentication required'}
    }
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def get_my_organizations(request):
    @sync_to_async
    def _sync_logic():
        user = request.user

        # Get organizations where user is owner
        from django.db.models import Count
        owned_orgs = Organization.objects.filter(owner=user, is_active=True).annotate(
            annotated_member_count=Count('members')
        )

        # Get organizations where user is member
        memberships = OrganizationMembership.objects.filter(
            user=user, 
            is_active=True
        ).select_related('organization', 'organization__owner').annotate(
            org_member_count=Count('organization__members')
        )

        organizations = []

        # Add owned organizations
        for org in owned_orgs:
            organizations.append({
                'id': str(org.id),
                'name': org.name,
                'role': 'owner',
                'is_owner': True,
                'member_count': org.annotated_member_count,
                'plan_type': org.plan_type,
                'joined_at': org.created_at.isoformat()
            })

        # Add member organizations
        for membership in memberships:
            # Skip if already added as owner
            if membership.organization.owner_id == user.id:
                continue

            organizations.append({
                'id': str(membership.organization.id),
                'name': membership.organization.name,
                'role': membership.role,
                'is_owner': False,
                'member_count': membership.org_member_count,
                'plan_type': membership.organization.plan_type,
                'joined_at': membership.joined_at.isoformat()
            })

        return Response({'organizations': organizations})

    return await _sync_logic()

@extend_schema(
    tags=["Organizations"],
    summary="Test Email",
    description="Test email configuration by sending a test email",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'email': {'type': 'string', 'description': 'Test email address'}
            },
            'required': ['email']
        }
    },
    responses={
        200: {
            'type': 'object',
            'properties': {
                'message': {'type': 'string'}
            }
        },
        400: {'description': 'Email required'},
        500: {'description': 'Email sending failed'}
    }
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
async def test_email(request):
    @sync_to_async
    def _sync_logic():
        from core.tasks import send_email_task
        from django.conf import settings

        email = request.data.get('email')

        if not email:
            return Response({'error': 'Email required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            send_email_task.delay(
                subject='Test Email from BuildTracker',
                message='This is a test email to verify email configuration is working.',
                recipient_list=[email],
                fail_silently=False,
            )
            return Response({'message': 'Test email sent successfully'})
        except Exception as e:
            return Response({'error': f'Failed to send email: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return await _sync_logic()

@extend_schema(
    tags=["Organizations"],
    summary="Get Invitation Details",
    description="Get invitation details using token (no authentication required)",
    responses={
        200: {
            'type': 'object',
            'properties': {
                'invitation': {
                    'type': 'object',
                    'properties': {
                        'email': {'type': 'string'},
                        'organization_name': {'type': 'string'},
                        'role': {'type': 'string'},
                        'invited_by': {'type': 'string'},
                        'expires_at': {'type': 'string'},
                        'is_valid': {'type': 'boolean'}
                    }
                }
            }
        },
        400: {'description': 'Invalid or expired invitation token'}
    }
)
@api_view(['GET'])
@permission_classes([permissions.AllowAny])
async def get_invitation_details(request, token):
    @sync_to_async
    def _sync_logic():
        try:
            invitation = OrganizationInvitation.objects.get(token=token)

            return Response({
                'invitation': {
                    'email': invitation.email,
                    'organization_name': invitation.organization.name,
                    'role': invitation.role,
                    'invited_by': f"{invitation.invited_by.first_name} {invitation.invited_by.last_name}".strip() or invitation.invited_by.email,
                    'expires_at': invitation.expires_at.isoformat(),
                    'is_valid': invitation.is_valid()
                }
            })

        except OrganizationInvitation.DoesNotExist:
            return Response({'error': 'Invalid invitation token'}, status=status.HTTP_400_BAD_REQUEST)
    return await _sync_logic()

