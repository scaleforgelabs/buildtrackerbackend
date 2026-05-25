from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework.decorators import permission_classes, parser_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from django.contrib.auth import authenticate, get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from django.db import transaction
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from utils import (
    sanitize_input, validate_password, 
    validate_email_format, validate_organization_name, rate_limit_key
)
from core.messaging import send_dual_notification
import secrets
import logging
from rate_limiting import rate_limit

logger = logging.getLogger(__name__)

def generate_otp():
    """Generate a cryptographically secure 4-digit OTP code"""
    return f"{secrets.randbelow(10000):04d}"

def send_otp_notification(user_or_email, otp):
    """Send OTP notification (Email + SMS)"""
    logger.info(f"OTP sent to {user_or_email}")
    
    subject = 'BuildTracker - Verify Your Email'
    message = f'Your verification code is: {otp}\n\nThis code expires in 5 minutes.'
    
    if isinstance(user_or_email, str):
        # If only email provided, limited to Email only or need to find user
        User = get_user_model()
        try:
            user = User.objects.get(email=user_or_email)
            send_dual_notification(user, subject, message, fail_silently=True)
        except User.DoesNotExist:
            from core.tasks import send_email_task
            send_email_task.delay(
                subject=subject,
                message=message,
                recipient_list=[user_or_email],
                fail_silently=True,
            )
    else:
        # User object provided
        send_dual_notification(user_or_email, subject, message, fail_silently=True)

User = get_user_model()

@extend_schema(
    tags=["Authentication"],
    summary="User Registration",
    description="Register a new user with optional organization creation - Supports both JSON and form-data",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'email': {'type': 'string', 'description': 'User email address'},
                'password': {'type': 'string', 'description': 'User password'},
                'first_name': {'type': 'string', 'description': 'User first name'},
                'last_name': {'type': 'string', 'description': 'User last name'},
                'organization_name': {'type': 'string', 'description': 'Optional organization name'}
            },
            'required': ['email', 'password']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'email': {'type': 'string', 'description': 'User email address'},
                'password': {'type': 'string', 'description': 'User password'},
                'first_name': {'type': 'string', 'description': 'User first name'},
                'last_name': {'type': 'string', 'description': 'User last name'},
                'organization_name': {'type': 'string', 'description': 'Optional organization name'}
            },
            'required': ['email', 'password']
        }
    },
    responses={
        201: {
            'type': 'object',
            'properties': {
                'user': {
                    'type': 'object',
                    'properties': {
                        'id': {'type': 'integer'},
                        'email': {'type': 'string'},
                        'first_name': {'type': 'string'},
                        'last_name': {'type': 'string'},
                        'avatar': {'type': 'string', 'nullable': True}
                    }
                },
                'token': {'type': 'string'},
                'refresh_token': {'type': 'string'},
                'organization': {'type': 'object', 'nullable': True}
            }
        },
        400: {'description': 'Invalid input or email already exists'},
        500: {'description': 'Registration failed'}
    }
)
@api_view(['POST'])
@parser_classes([JSONParser, MultiPartParser, FormParser])
@permission_classes([AllowAny])
@rate_limit(requests_per_minute=5)
async def register_view(request):
    @sync_to_async
    def _sync_logic():
        email = sanitize_input(request.data.get('email', ''), 254).lower()
        password = request.data.get('password', '')
        first_name = sanitize_input(request.data.get('first_name', ''), 30)
        last_name = sanitize_input(request.data.get('last_name', ''), 30)
        organization_name = sanitize_input(request.data.get('organization_name', ''), 100)

        if not email or not password:
            return Response({'error': 'Email and password required'}, status=status.HTTP_400_BAD_REQUEST)

        is_valid, error_msg = validate_email_format(email)
        if not is_valid:
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)

        is_valid, error_msg = validate_password(password)
        if not is_valid:
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)

        if organization_name:
            is_valid, error_msg = validate_organization_name(organization_name)
            if not is_valid:
                return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                if User.objects.filter(email=email).exists():
                    return Response({'error': 'Email already exists'}, status=status.HTTP_400_BAD_REQUEST)

                user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    status='trial'
                )

            # Generate and send OTP
            otp = generate_otp()
            cache_key = f'otp:{user.email}'
            cache.set(cache_key, otp, timeout=300)  # 5 minutes
            send_otp_notification(user.email, otp)

            response_data = {
                'user': {
                    'id': str(user.id),
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'avatar': user.avatar.url if user.avatar else None,
                    'last_active_workspace': str(user.last_active_workspace) if user.last_active_workspace else None
                },
                'message': 'Registration successful. Please verify your email with the OTP sent.'
            }

            return Response(response_data, status=status.HTTP_201_CREATED)

        except Exception as e:
            from utils import handle_view_exception
            return handle_view_exception(e, 'auth_func.views.auth_new.register_view')

    return await _sync_logic()

@extend_schema(
    tags=["Authentication"],
    summary="Register with Invitation",
    description="Register a new user using an organization invitation token",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'email': {'type': 'string', 'description': 'User email address'},
                'password': {'type': 'string', 'description': 'User password'},
                'first_name': {'type': 'string', 'description': 'User first name'},
                'last_name': {'type': 'string', 'description': 'User last name'},
                'invitation_token': {'type': 'string', 'description': 'Organization invitation token'}
            },
            'required': ['email', 'password', 'invitation_token']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'email': {'type': 'string', 'description': 'User email address'},
                'password': {'type': 'string', 'description': 'User password'},
                'first_name': {'type': 'string', 'description': 'User first name'},
                'last_name': {'type': 'string', 'description': 'User last name'},
                'invitation_token': {'type': 'string', 'description': 'Organization invitation token'}
            },
            'required': ['email', 'password', 'invitation_token']
        }
    },
    responses={
        201: {
            'type': 'object',
            'properties': {
                'user': {
                    'type': 'object',
                    'properties': {
                        'id': {'type': 'integer'},
                        'email': {'type': 'string'},
                        'first_name': {'type': 'string'},
                        'last_name': {'type': 'string'},
                        'avatar': {'type': 'string', 'nullable': True}
                    }
                },
                'token': {'type': 'string'},
                'refresh_token': {'type': 'string'},
                'organization': {'type': 'object'}
            }
        },
        400: {'description': 'Invalid input, email mismatch, or invalid invitation'},
        500: {'description': 'Registration failed'}
    }
)
@api_view(['POST'])
@parser_classes([JSONParser, MultiPartParser, FormParser])
@permission_classes([AllowAny])
@rate_limit(requests_per_minute=5)
async def register_with_invitation_view(request):
    @sync_to_async
    def _sync_logic():
        from organizations.models import OrganizationInvitation

        email = sanitize_input(request.data.get('email', ''), 254).lower()
        password = request.data.get('password', '')
        first_name = sanitize_input(request.data.get('first_name', ''), 30)
        last_name = sanitize_input(request.data.get('last_name', ''), 30)
        invitation_token = request.data.get('invitation_token', '')

        if not email or not password or not invitation_token:
            return Response({'error': 'Email, password, and invitation token required'}, status=status.HTTP_400_BAD_REQUEST)

        is_valid, error_msg = validate_email_format(email)
        if not is_valid:
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)

        is_valid, error_msg = validate_password(password)
        if not is_valid:
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)

        try:
            invitation = OrganizationInvitation.objects.get(token=invitation_token)

            if not invitation.is_valid():
                return Response({'error': 'Invalid or expired invitation'}, status=status.HTTP_400_BAD_REQUEST)

            if invitation.email.lower() != email:
                return Response({'error': 'Email does not match invitation'}, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                if User.objects.filter(email=email).exists():
                    return Response({'error': 'Email already exists'}, status=status.HTTP_400_BAD_REQUEST)

                user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name
                )

            # Generate and send OTP
            otp = generate_otp()
            cache_key = f'otp:{user.email}'
            cache.set(cache_key, otp, timeout=300)  # 5 minutes
            send_otp_notification(user.email, otp)

            response_data = {
                'user': {
                    'id': str(user.id),
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'avatar': user.avatar.url if user.avatar else None,
                    'last_active_workspace': str(user.last_active_workspace) if user.last_active_workspace else None
                },
                'message': 'Registration successful. Please verify your email with the OTP sent.'
            }

            return Response(response_data, status=status.HTTP_201_CREATED)

        except OrganizationInvitation.DoesNotExist:
            return Response({'error': 'Invalid invitation token'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': f'Registration failed: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return await _sync_logic()

@extend_schema(
    tags=["Authentication"],
    summary="Register with Workspace Invitation",
    description="Register a new user using a workspace invitation token. After OTP verification, the user is auto-added to the workspace.",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'email': {'type': 'string'},
                'password': {'type': 'string'},
                'first_name': {'type': 'string'},
                'last_name': {'type': 'string'},
                'invitation_token': {'type': 'string', 'description': 'Workspace invitation token'}
            },
            'required': ['email', 'password', 'invitation_token']
        }
    },
    responses={
        201: {'description': 'User registered, OTP sent. Workspace will be joined after OTP verification.'},
        400: {'description': 'Invalid input or invitation'},
        500: {'description': 'Registration failed'}
    }
)
@api_view(['POST'])
@parser_classes([JSONParser, MultiPartParser, FormParser])
@permission_classes([AllowAny])
@rate_limit(requests_per_minute=5)
async def register_with_workspace_invitation_view(request):
    @sync_to_async
    def _sync_logic():
        from workspaces.models import WorkspaceInvitation

        email = sanitize_input(request.data.get('email', ''), 254).lower()
        password = request.data.get('password', '')
        first_name = sanitize_input(request.data.get('first_name', ''), 30)
        last_name = sanitize_input(request.data.get('last_name', ''), 30)
        invitation_token = request.data.get('invitation_token', '')

        if not email or not password or not invitation_token:
            return Response({'error': 'Email, password, and invitation token required'}, status=status.HTTP_400_BAD_REQUEST)

        is_valid, error_msg = validate_email_format(email)
        if not is_valid:
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)

        is_valid, error_msg = validate_password(password)
        if not is_valid:
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)

        try:
            invitation = WorkspaceInvitation.objects.get(token=invitation_token)

            if not invitation.is_valid():
                return Response({'error': 'Invalid or expired invitation'}, status=status.HTTP_400_BAD_REQUEST)

            if invitation.email.lower() != email:
                return Response({'error': 'Email does not match invitation'}, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                if User.objects.filter(email=email).exists():
                    return Response({'error': 'Email already exists. Please login instead.'}, status=status.HTTP_400_BAD_REQUEST)

                user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name
                )

            # Generate and send OTP
            otp = generate_otp()
            cache_key = f'otp:{user.email}'
            cache.set(cache_key, otp, timeout=300)  # 5 minutes
            send_otp_notification(user.email, otp)

            # Store workspace invitation token for auto-accept after OTP verification
            ws_invite_key = f'ws_invite:{user.email}'
            cache.set(ws_invite_key, invitation_token, timeout=3600)  # 1 hour

            print(f"\n{'='*60}")
            print("📝 New user registered via workspace invitation")
            print(f"   Email: {email}")
            print(f"   Workspace: {invitation.workspace.name}")
            print(f"   Role: {invitation.role}")
            print("   OTP sent — awaiting verification")
            print(f"{'='*60}\n")

            return Response({
                'user': {
                    'id': str(user.id),
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'last_active_workspace': user.last_active_workspace
                },
                'message': 'Registration successful. Please verify your email with the OTP sent.',
                'workspace_name': invitation.workspace.name
            }, status=status.HTTP_201_CREATED)

        except WorkspaceInvitation.DoesNotExist:
            return Response({'error': 'Invalid invitation token'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': f'Registration failed: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return await _sync_logic()

@extend_schema(
    tags=["Authentication"],
    summary="User Login",
    description="User login - Supports both JSON and form-data",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'email': {'type': 'string', 'description': 'User email'},
                'password': {'type': 'string', 'description': 'User password'}
            },
            'required': ['email', 'password']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'email': {'type': 'string', 'description': 'User email'},
                'password': {'type': 'string', 'description': 'User password'}
            },
            'required': ['email', 'password']
        }
    },
    responses={
        200: {
            'type': 'object',
            'properties': {
                'user': {
                    'type': 'object',
                    'properties': {
                        'id': {'type': 'integer'},
                        'email': {'type': 'string'},
                        'first_name': {'type': 'string'},
                        'last_name': {'type': 'string'},
                        'avatar': {'type': 'string', 'nullable': True}
                    }
                },
                'token': {'type': 'string'},
                'refresh_token': {'type': 'string'},
                'organization': {'type': 'object', 'nullable': True}
            }
        },
        400: {'description': 'Email and password required'},
        401: {'description': 'Invalid credentials'}
    }
)
@api_view(['POST'])
@parser_classes([JSONParser, MultiPartParser, FormParser])
@permission_classes([AllowAny])
@rate_limit(requests_per_minute=5)
async def login_view(request):
    @sync_to_async
    def _sync_logic():
        email = sanitize_input(request.data.get('email', ''), 254).lower()
        password = request.data.get('password', '')

        if not email or not password:
            return Response({'error': 'Email and password required'}, status=status.HTTP_400_BAD_REQUEST)

        is_valid, error_msg = validate_email_format(email)
        if not is_valid:
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

        if len(password) > 128:
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            # Use get() with no is_active filter so we can find soft-deleted accounts
            user = User.objects.get(email=email)

            # Check if user has verified their email
            if not user.is_verified:
                return Response(
                    {'error': 'Please verify your email first. Check your inbox for the OTP.', 'requires_verification': True, 'email': email},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Restore soft-deleted account if within the 30-day grace period
            from django.utils import timezone as tz
            if user.scheduled_for_deletion_at and not user.is_active:
                if tz.now() <= user.scheduled_for_deletion_at:
                    # Verify password manually since authenticate() skips inactive users
                    if user.check_password(password):
                        user.scheduled_for_deletion_at = None
                        user.is_active = True
                        user.save(update_fields=['scheduled_for_deletion_at', 'is_active', 'updated_at'])
                        refresh = RefreshToken.for_user(user)
                        return Response({
                            'user': {
                                'id': str(user.id),
                                'email': user.email,
                                'first_name': user.first_name,
                                'last_name': user.last_name,
                                'avatar': user.avatar.url if user.avatar else None,
                                'last_active_workspace': user.last_active_workspace,
                                'scheduled_for_deletion_at': None,
                            },
                            'token': str(refresh.access_token),
                            'refresh_token': str(refresh),
                            'account_restored': True,
                        })
                # Grace period expired — account is permanently gone
                return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

            user = authenticate(username=user.username, password=password)
            if user and user.is_active:
                refresh = RefreshToken.for_user(user)

                response_data = {
                    'user': {
                        'id': str(user.id),
                        'email': user.email,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'avatar': user.avatar.url if user.avatar else None,
                        'last_active_workspace': user.last_active_workspace,
                        'scheduled_for_deletion_at': user.scheduled_for_deletion_at.isoformat() if user.scheduled_for_deletion_at else None,
                    },
                    'token': str(refresh.access_token),
                    'refresh_token': str(refresh)
                }

                return Response(response_data)
        except User.DoesNotExist:
            pass

        return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

    return await _sync_logic()

@extend_schema(
    tags=["Authentication"],
    summary="Verify OTP",
    description="Verify the OTP sent to user's email after registration",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'email': {'type': 'string', 'description': 'User email'},
                'otp': {'type': 'string', 'description': '4-digit OTP code'}
            },
            'required': ['email', 'otp']
        }
    },
    responses={
        200: {
            'type': 'object',
            'properties': {
                'user': {'type': 'object'},
                'token': {'type': 'string'},
                'refresh_token': {'type': 'string'},
                'message': {'type': 'string'}
            }
        },
        400: {'description': 'Invalid or expired OTP'},
        404: {'description': 'User not found'}
    }
)
@api_view(['POST'])
@permission_classes([AllowAny])
async def verify_otp_view(request):
    @sync_to_async
    def _sync_logic():
        email = sanitize_input(request.data.get('email', ''), 254).lower()
        otp = request.data.get('otp', '').strip()

        if not email or not otp:
            return Response({'error': 'Email and OTP required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        if user.is_verified:
            return Response({'error': 'Account already verified'}, status=status.HTTP_400_BAD_REQUEST)

        cache_key = f'otp:{email}'
        cached_otp = cache.get(cache_key)

        if not cached_otp:
            return Response({'error': 'OTP expired. Please request a new one.'}, status=status.HTTP_400_BAD_REQUEST)

        if str(cached_otp) != str(otp):
            return Response({'error': 'Invalid OTP code'}, status=status.HTTP_400_BAD_REQUEST)

        # OTP is valid — verify user and issue tokens
        user.is_verified = True
        user.save()
        cache.delete(cache_key)

        refresh = RefreshToken.for_user(user)

        print(f"\n{'='*50}")
        print(f"✅ User {email} verified successfully!")
        print(f"{'='*50}\n")

        # Check for pending workspace invitation and auto-accept
        workspace_joined = None
        ws_invite_key = f'ws_invite:{email}'
        ws_invite_token = cache.get(ws_invite_key)
        if ws_invite_token:
            try:
                from workspaces.models import WorkspaceInvitation, WorkspaceMember
                invitation = WorkspaceInvitation.objects.get(token=ws_invite_token)
                if invitation.is_valid() and invitation.email.lower() == email:
                    # Auto-accept the invitation
                    if not WorkspaceMember.objects.filter(workspace=invitation.workspace, user=user).exists():
                        WorkspaceMember.objects.create(
                            workspace=invitation.workspace,
                            user=user,
                            role=invitation.role,
                            phone=invitation.phone or '',
                            job_role=invitation.job_role or '',
                            user_status=invitation.user_status or 'active',
                            email=user.email
                        )
                    invitation.status = 'accepted'
                    invitation.save()
                    workspace_joined = {
                        'id': str(invitation.workspace.id),
                        'name': invitation.workspace.name
                    }
                    print(f"\n{'='*50}")
                    print("🎉 Auto-accepted workspace invitation!")
                    print(f"   User: {email}")
                    print(f"   Workspace: {invitation.workspace.name}")
                    print(f"   Role: {invitation.role}")
                    print(f"{'='*50}\n")
                cache.delete(ws_invite_key)
            except Exception as e:
                print(f"⚠️ Failed to auto-accept workspace invitation: {e}")
                cache.delete(ws_invite_key)

        response_data = {
            'user': {
                'id': str(user.id),
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'avatar': user.avatar.url if user.avatar else None,
                'last_active_workspace': user.last_active_workspace
            },
            'token': str(refresh.access_token),
            'refresh_token': str(refresh),
            'message': 'Email verified successfully'
        }

        if workspace_joined:
            response_data['workspace_joined'] = workspace_joined

        return Response(response_data)

    return await _sync_logic()

@extend_schema(
    tags=["Authentication"],
    summary="Resend OTP",
    description="Resend OTP verification code to user's email",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'email': {'type': 'string', 'description': 'User email'}
            },
            'required': ['email']
        }
    },
    responses={
        200: {'type': 'object', 'properties': {'message': {'type': 'string'}}},
        400: {'description': 'Invalid request'},
        404: {'description': 'User not found'},
        429: {'description': 'Rate limit exceeded'}
    }
)
@api_view(['POST'])
@permission_classes([AllowAny])
async def resend_otp_view(request):
    @sync_to_async
    def _sync_logic():
        email = sanitize_input(request.data.get('email', ''), 254).lower()

        if not email:
            return Response({'error': 'Email required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        if user.is_verified:
            return Response({'error': 'Account already verified'}, status=status.HTTP_400_BAD_REQUEST)

        # Rate limiting — 60 second cooldown
        rate_key = f'otp_resend:{email}'
        if cache.get(rate_key):
            return Response(
                {'error': 'Please wait before requesting another OTP'},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        otp = generate_otp()
        cache_key = f'otp:{email}'
        cache.set(cache_key, otp, timeout=300)  # 5 minutes
        cache.set(rate_key, True, timeout=60)   # 60 second cooldown
        send_otp_notification(user, otp)

        return Response({'message': 'OTP sent successfully'})

    return await _sync_logic()

@extend_schema(
    tags=["Authentication"],
    summary="User Logout",
    description="Logout user and blacklist refresh token",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'refresh_token': {'type': 'string', 'description': 'Refresh token to blacklist'}
            }
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'refresh_token': {'type': 'string', 'description': 'Refresh token to blacklist'}
            }
        }
    },
    responses={
        200: {
            'type': 'object',
            'properties': {
                'message': {'type': 'string'}
            }
        }
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
async def logout_view(request):
    @sync_to_async
    def _sync_logic():
        try:
            refresh_token = request.data.get('refresh_token')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            return Response({'message': 'Logged out successfully'})
        except Exception:
            return Response({'message': 'Logged out successfully'})

    return await _sync_logic()

@extend_schema(
    tags=["Authentication"],
    summary="Refresh Token",
    description="Generate new access token using refresh token",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'refresh_token': {'type': 'string', 'description': 'Valid refresh token'}
            },
            'required': ['refresh_token']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'refresh_token': {'type': 'string', 'description': 'Valid refresh token'}
            },
            'required': ['refresh_token']
        }
    },
    responses={
        200: {
            'type': 'object',
            'properties': {
                'token': {'type': 'string'},
                'refresh_token': {'type': 'string'}
            }
        },
        400: {'description': 'Refresh token required'},
        401: {'description': 'Invalid refresh token'}
    }
)
@api_view(['POST'])
@permission_classes([AllowAny])
async def refresh_token_view(request):
    @sync_to_async
    def _sync_logic():
        refresh_token = request.data.get('refresh_token')

        if not refresh_token:
            return Response({'error': 'Refresh token required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            refresh = RefreshToken(refresh_token)
            return Response({
                'token': str(refresh.access_token),
                'refresh_token': str(refresh)
            })
        except Exception:
            return Response({'error': 'Invalid refresh token'}, status=status.HTTP_401_UNAUTHORIZED)

    return await _sync_logic()

@extend_schema(
    tags=["Authentication"],
    summary="Forgot Password",
    description="Send password reset email to user",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'email': {'type': 'string', 'description': 'User email address'}
            },
            'required': ['email']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'email': {'type': 'string', 'description': 'User email address'}
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
        400: {'description': 'Email required or invalid email format'},
        429: {'description': 'Rate limit exceeded'}
    }
)
@api_view(['POST'])
@permission_classes([AllowAny])
@rate_limit(requests_per_minute=5)
async def forgot_password_view(request):
    @sync_to_async
    def _sync_logic():
        email = sanitize_input(request.data.get('email', ''), 254).lower()

        if not email:
            return Response({'error': 'Email required'}, status=status.HTTP_400_BAD_REQUEST)

        is_valid, error_msg = validate_email_format(email)
        if not is_valid:
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)

        rate_key = rate_limit_key(email, 'forgot_password')
        if cache.get(rate_key):
            return Response(
                {'error': 'Please wait before requesting another password reset'}, 
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        try:
            user = User.objects.get(email=email)
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))

            reset_url = f"{settings.FRONTEND_URL}/reset-password/{uid}/{token}"

            subject = 'Password Reset Request'
            message = f'Click the link to reset your password: {reset_url}'

            send_dual_notification(
                user=user,
                subject=subject,
                message=message,
            )

            cache.set(rate_key, True, 300)

        except User.DoesNotExist:
            pass

        return Response({'message': 'Password reset email sent'})

    return await _sync_logic()

@extend_schema(
    tags=["Authentication"],
    summary="Reset Password",
    description="Reset user password using token from email",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'uid': {'type': 'string', 'description': 'Base64 encoded user ID'},
                'token': {'type': 'string', 'description': 'Password reset token'},
                'password': {'type': 'string', 'description': 'New password'}
            },
            'required': ['uid', 'token', 'password']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'uid': {'type': 'string', 'description': 'Base64 encoded user ID'},
                'token': {'type': 'string', 'description': 'Password reset token'},
                'password': {'type': 'string', 'description': 'New password'}
            },
            'required': ['uid', 'token', 'password']
        }
    },
    responses={
        200: {
            'type': 'object',
            'properties': {
                'message': {'type': 'string'}
            }
        },
        400: {'description': 'Token and password required, invalid token, or password validation failed'}
    }
)
@api_view(['POST'])
@permission_classes([AllowAny])
async def reset_password_view(request):
    @sync_to_async
    def _sync_logic():
        uid = request.data.get('uid')
        token = request.data.get('token')
        password = request.data.get('password')

        if not uid or not token or not password:
            return Response({'error': 'UID, token and password required'}, status=status.HTTP_400_BAD_REQUEST)

        is_valid, error_msg = validate_password(password)
        if not is_valid:
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)

            if default_token_generator.check_token(user, token):
                user.set_password(password)
                user.save()
                return Response({'message': 'Password reset successfully'})
            else:
                return Response({'error': 'Invalid or expired token'}, status=status.HTTP_400_BAD_REQUEST)

        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            return Response({'error': 'Invalid token or user ID'}, status=status.HTTP_400_BAD_REQUEST)

    return await _sync_logic()

@extend_schema(
    tags=["Authentication"],
    summary="Get Current User",
    description="Get current authenticated user information with organization details",
    responses={
        200: {
            'type': 'object',
            'properties': {
                'user': {
                    'type': 'object',
                    'properties': {
                        'id': {'type': 'integer'},
                        'email': {'type': 'string'},
                        'first_name': {'type': 'string'},
                        'last_name': {'type': 'string'},
                        'role': {'type': 'string'},
                        'phone': {'type': 'string'},
                        'bio': {'type': 'string'},
                        'avatar': {'type': 'string', 'nullable': True}
                    }
                },
                'organization': {'type': 'object', 'nullable': True},
                'usage': {'type': 'object', 'nullable': True}
            }
        },
        401: {'description': 'Authentication required'}
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
async def me_view(request):
    @sync_to_async
    def _sync_logic():
        user = request.user

        response_data = {
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'role': user.role,
                'phone': user.phone,
                'bio': user.bio,
                'avatar': user.avatar.url if user.avatar else None,
                'last_active_workspace': user.last_active_workspace,
                'platform_role': user.platform_role,
                'scheduled_for_deletion_at': user.scheduled_for_deletion_at.isoformat() if user.scheduled_for_deletion_at else None,
            }
        }

        return Response(response_data)

    return await _sync_logic()

@extend_schema(
    tags=["Authentication"],
    summary="Update User Profile",
    description="Update current user profile information",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'first_name': {'type': 'string', 'description': 'User first name'},
                'last_name': {'type': 'string', 'description': 'User last name'},
                'avatar_url': {'type': 'string', 'description': 'Avatar URL'}
            }
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'first_name': {'type': 'string', 'description': 'User first name'},
                'last_name': {'type': 'string', 'description': 'User last name'},
                'avatar_url': {'type': 'string', 'description': 'Avatar URL'}
            }
        }
    },
    responses={
        200: {
            'type': 'object',
            'properties': {
                'user': {
                    'type': 'object',
                    'properties': {
                        'id': {'type': 'integer'},
                        'email': {'type': 'string'},
                        'first_name': {'type': 'string'},
                        'last_name': {'type': 'string'},
                        'avatar': {'type': 'string', 'nullable': True}
                    }
                }
            }
        },
        401: {'description': 'Authentication required'}
    }
)
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
async def update_profile_view(request):
    @sync_to_async
    def _sync_logic():
        user = request.user

        first_name = sanitize_input(request.data.get('first_name', ''), 30)
        last_name = sanitize_input(request.data.get('last_name', ''), 30)
        avatar_url = sanitize_input(request.data.get('avatar_url', ''), 500)

        if first_name:
            user.first_name = first_name
        if last_name:
            user.last_name = last_name
        if avatar_url:
            user.avatar = avatar_url

        user.save()

        return Response({
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'avatar': user.avatar.url if user.avatar else None,
                'last_active_workspace': user.last_active_workspace
            }
        })

    return await _sync_logic()

@extend_schema(
    tags=["Authentication"],
    summary="Create Organization",
    description="Create a new organization for the authenticated user",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string', 'description': 'Organization name'}
            },
            'required': ['name']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string', 'description': 'Organization name'}
            },
            'required': ['name']
        }
    },
    responses={
        201: {
            'type': 'object',
            'properties': {
                'organization': {'type': 'object'},
                'message': {'type': 'string'}
            }
        },
        400: {'description': 'Invalid organization name or user already owns an organization'},
        401: {'description': 'Authentication required'}
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
async def create_organization_view(request):
    @sync_to_async
    def _sync_logic():

        organization_name = sanitize_input(request.data.get('name', ''), 100)

        if not organization_name:
            return Response({'error': 'Organization name required'}, status=status.HTTP_400_BAD_REQUEST)

        is_valid, error_msg = validate_organization_name(organization_name)
        if not is_valid:
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'error': 'User = Organization architecture - no separate organization creation needed'}, status=status.HTTP_400_BAD_REQUEST)
    return await _sync_logic()

