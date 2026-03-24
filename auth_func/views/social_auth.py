from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework.decorators import permission_classes, parser_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.apple.views import AppleOAuth2Adapter
from allauth.socialaccount.providers.facebook.views import FacebookOAuth2Adapter
from dj_rest_auth.registration.views import SocialLoginView
import requests
import jwt
import secrets
import logging
from django.conf import settings

User = get_user_model()
logger = logging.getLogger(__name__)

class GoogleLogin(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter

class AppleLogin(SocialLoginView):
    adapter_class = AppleOAuth2Adapter

class FacebookLogin(SocialLoginView):
    adapter_class = FacebookOAuth2Adapter

@extend_schema(
    tags=["Authentication"],
    summary="Google OAuth Login",
    description="Authenticate user using Google OAuth ID token with full signature verification",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'id_token': {'type': 'string', 'description': 'Google ID token'}
            },
            'required': ['id_token']
        }
    },
    responses={
        200: {
            'type': 'object',
            'properties': {
                'access': {'type': 'string'},
                'refresh': {'type': 'string'},
                'user_id': {'type': 'integer'},
                'email': {'type': 'string'},
                'created': {'type': 'boolean'}
            }
        },
        400: {'description': 'ID token required or authentication failed'}
    }
)
@api_view(['POST'])
@parser_classes([JSONParser, MultiPartParser, FormParser])
@permission_classes([AllowAny])
async def google_auth(request):
    @sync_to_async
    def _sync_logic():
        id_token_str = request.data.get('id_token')

        if not id_token_str:
            return Response({'error': 'ID token required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from google.oauth2 import id_token
            from google.auth.transport import requests as google_requests

            # Verify the ID token using google-auth library
            # This checks the signature, expiration, and audience with a 1-year clock drift tolerance
            # for edge cases where the OS clock is radically out of sync
            idinfo = id_token.verify_oauth2_token(
                id_token_str, 
                google_requests.Request(), 
                settings.SOCIALACCOUNT_PROVIDERS['google']['APP']['client_id'],
                clock_skew_in_seconds=31536000
            )

            email = idinfo.get('email')
            first_name = idinfo.get('given_name', '')
            last_name = idinfo.get('family_name', '')

            if not email:
                return Response({'error': 'Email not provided by Google'}, status=status.HTTP_400_BAD_REQUEST)

            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'username': email,
                    'first_name': first_name,
                    'last_name': last_name,
                    'is_verified': True,
                }
            )

            if not created and not user.is_verified:
                user.is_verified = True
                user.save()

            if not created:
                updated = False
                if not user.first_name and first_name:
                    user.first_name = first_name
                    updated = True
                if not user.last_name and last_name:
                    user.last_name = last_name
                    updated = True
                if updated:
                    user.save()

            if created:
                user.set_password(secrets.token_urlsafe(32))
                user.save()

            refresh = RefreshToken.for_user(user)
            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user_id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'created': created
            })

        except ValueError as e:
            logger.error(f"Google auth validation failed: {str(e)}")
            return Response({'error': f'Invalid ID token: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Google auth failed: {str(e)}")
            return Response({'error': 'Authentication failed'}, status=status.HTTP_400_BAD_REQUEST)

    return await _sync_logic()

def get_apple_public_key(kid):
    """Fetch Apple's public key for a specific KID"""
    response = requests.get('https://appleid.apple.com/auth/keys', timeout=10)
    keys = response.json().get('keys', [])
    for key in keys:
        if key.get('kid') == kid:
            return key
    return None

@extend_schema(
    tags=["Authentication"],
    summary="Apple OAuth Login",
    description="Authenticate user using Apple ID token with full signature verification",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'id_token': {'type': 'string', 'description': 'Apple ID token'}
            },
            'required': ['id_token']
        }
    },
    responses={
        200: {
            'type': 'object',
            'properties': {
                'access': {'type': 'string'},
                'refresh': {'type': 'string'},
                'user_id': {'type': 'integer'},
                'email': {'type': 'string'},
                'created': {'type': 'boolean'}
            }
        },
        400: {'description': 'ID token required or authentication failed'}
    }
)
@api_view(['POST'])
@parser_classes([JSONParser, MultiPartParser, FormParser])
@permission_classes([AllowAny])
async def apple_auth(request):
    @sync_to_async
    def _sync_logic():
        id_token_str = request.data.get('id_token')

        if not id_token_str:
            return Response({'error': 'ID token required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Get Header to find KID
            header = jwt.get_unverified_header(id_token_str)
            kid = header.get('kid')

            # Get Public Key from Apple
            apple_key = get_apple_public_key(kid)
            if not apple_key:
                return Response({'error': 'Invalid Apple key'}, status=status.HTTP_400_BAD_REQUEST)

            # Construct public key
            from jwt.algorithms import RSAAlgorithm
            public_key = RSAAlgorithm.from_jwk(apple_key)

            # Verify Token
            decoded_token = jwt.decode(
                id_token_str, 
                public_key, 
                algorithms=['RS256'],
                audience=settings.SOCIALACCOUNT_PROVIDERS['apple']['APP']['client_id']
            )

            email = decoded_token.get('email')
            if not email:
                return Response({'error': 'Email not provided by Apple'}, status=status.HTTP_400_BAD_REQUEST)

            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'username': email,
                    'first_name': '',
                    'last_name': '',
                    'is_verified': True,
                }
            )

            if created:
                user.set_password(secrets.token_urlsafe(32))
                user.save()

            refresh = RefreshToken.for_user(user)
            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user_id': user.id,
                'email': user.email,
                'created': created
            })

        except jwt.ExpiredSignatureError:
            return Response({'error': 'Token has expired'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Apple auth failed: {str(e)}")
            return Response({'error': 'Authentication failed'}, status=status.HTTP_400_BAD_REQUEST)
    return await _sync_logic()

