from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework.decorators import permission_classes, parser_classes
from rest_framework.permissions import *
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from django.contrib.auth import authenticate
from rest_framework import permissions
from django.contrib.auth import authenticate, get_user_model
from drf_spectacular.utils import extend_schema
from utils import sanitize_input, validate_password
import json

User = get_user_model()

@extend_schema(
    tags=["Authentication"],
    methods=['PATCH'],
    description="Update user profile - Supports both JSON and form-data",
    request={
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'username': {'type': 'string', 'description': 'Username'},
                'email': {'type': 'string', 'description': 'Email address'},
                'first_name': {'type': 'string', 'description': 'First name'},
                'last_name': {'type': 'string', 'description': 'Last name'},
                'role': {'type': 'string', 'description': 'User role'},
                'phone': {'type': 'string', 'description': 'Phone number'},
                'bio': {'type': 'string', 'description': 'User biography'},
                'avatar': {'type': 'string', 'format': 'binary', 'description': 'Profile picture'}
            }
        }
    },
    responses={
        200: {
            'type': 'object',
            'properties': {
                'message': {'type': 'string'},
                'user': {
                    'type': 'object',
                    'properties': {
                        'username': {'type': 'string'},
                        'email': {'type': 'string'},
                        'first_name': {'type': 'string'},
                        'last_name': {'type': 'string'},
                        'role': {'type': 'string'},
                        'phone': {'type': 'string'},
                        'bio': {'type': 'string'},
                        'avatar': {'type': 'string'}
                    }
                }
            }
        }
    }
)
@api_view(['GET', 'PATCH'])
@parser_classes([JSONParser, MultiPartParser, FormParser])
@permission_classes([permissions.IsAuthenticated])
async def user_profile(request):
    @sync_to_async
    def _sync_logic():
        if request.method == 'GET':
            user_id = request.user.id
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    return Response({
                        'username': user.username,
                        'email': user.email,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'role': user.role,
                        'phone': user.phone,
                        'bio': user.bio,
                        'avatar': user.avatar.url if user.avatar else None,
                        'date_joined': user.date_joined
                    })
                except User.DoesNotExist:
                    return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'error': 'User ID not provided'}, status=status.HTTP_400_BAD_REQUEST)
        elif request.method == 'PATCH':
            user = request.user

            try:
                for field, value in request.data.items():
                    if field == 'username' and value:
                        sanitized_username = sanitize_input(value, 30).lower()
                        if sanitized_username != user.username:
                            if User.objects.filter(username=sanitized_username).exists():
                                return Response({'error': 'Username already exists'}, status=status.HTTP_400_BAD_REQUEST)
                            user.username = sanitized_username

                    elif field == 'email' and value:
                        sanitized_email = sanitize_input(value, 254).lower()
                        if sanitized_email != user.email:
                            if User.objects.filter(email=sanitized_email).exists():
                                return Response({'error': 'Email already exists'}, status=status.HTTP_400_BAD_REQUEST)
                            user.email = sanitized_email

                    elif field == 'first_name' and value:
                        user.first_name = sanitize_input(value, 30).title()

                    elif field == 'last_name' and value:
                        user.last_name = sanitize_input(value, 30).title()

                    elif field == 'role':
                        user.role = sanitize_input(value, 100)

                    elif field == 'phone':
                        user.phone = sanitize_input(value, 20)

                    elif field == 'bio':
                        user.bio = sanitize_input(value, 1000)

                if 'avatar' in request.FILES:
                    user.avatar = request.FILES['avatar']

                user.save()

                return Response({
                    'message': 'Profile updated successfully',
                    'user': {
                        'username': user.username,
                        'email': user.email,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'role': user.role,
                        'phone': user.phone,
                        'bio': user.bio,
                        'avatar': user.avatar.url if user.avatar else None
                    }
                })

            except Exception as e:
                return Response({'error': f'Profile update failed: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            return Response({'error': 'Invalid request method'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)


    return await _sync_logic()

@extend_schema(
    tags=["Authentication"],
    methods=['POST'],
    description="Change user password",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'old_password': {'type': 'string', 'description': 'Current password'},
                'new_password': {'type': 'string', 'description': 'New password'}
            },
            'required': ['old_password', 'new_password']
        }
    },
    responses={
        200: {'description': 'Password changed successfully'},
        400: {'description': 'Invalid input or incorrect old password'}
    }
)
@api_view(['POST'])
@parser_classes([JSONParser, MultiPartParser, FormParser])
@permission_classes([permissions.IsAuthenticated])
async def change_password_view(request):
    @sync_to_async
    def _sync_logic():
        user = request.user
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')

        if not old_password or not new_password:
            return Response({'error': 'Both old and new passwords are required'}, status=status.HTTP_400_BAD_REQUEST)

        if not user.check_password(old_password):
            return Response({'error': 'Incorrect old password'}, status=status.HTTP_400_BAD_REQUEST)

        is_valid, error_msg = validate_password(new_password)
        if not is_valid:
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()

        return Response({'message': 'Password changed successfully'}, status=status.HTTP_200_OK)
    return await _sync_logic()

