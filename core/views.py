from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework.decorators import permission_classes
from rest_framework.response import Response
from rest_framework import status, permissions
from drf_spectacular.utils import extend_schema
from drf_spectacular.openapi import OpenApiParameter, OpenApiTypes
from celery import shared_task
from django.core.cache import cache
from django.http import JsonResponse

@shared_task
def sample_task(message):
    """Sample Celery task"""
    return f"Task completed: {message}"

@extend_schema(
    summary="Get Cached Data",
    description="Get cached data or fetch new data",
    responses={
        200: {
            'type': 'object',
            'properties': {
                'message': {'type': 'string'},
                'cached': {'type': 'boolean'}
            }
        }
    }
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def cached_data(request):
    @sync_to_async
    def _sync_logic():
        """API endpoint that demonstrates caching"""
        cache_key = 'sample_data'
        data = cache.get(cache_key)

        if not data:
            data = {'message': 'Fresh data from database', 'cached': False}
            cache.set(cache_key, data, timeout=300)
        else:
            data['cached'] = True

        return Response(data)

    return await _sync_logic()

@extend_schema(
    summary="Trigger Celery Task",
    description="Trigger a Celery task",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'message': {'type': 'string', 'description': 'Message to process in the task'}
            },
            'required': ['message']
        }
    },
    responses={
        200: {
            'type': 'object',
            'properties': {
                'task_id': {'type': 'string'},
                'message': {'type': 'string'}
            }
        },
        400: {'description': 'Bad request'}
    }
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
async def trigger_task(request):
    @sync_to_async
    def _sync_logic():
        """API endpoint that triggers a Celery task"""
        message = request.data.get('message', 'Default message')
        task = sample_task.delay(message)

        return Response({
            'task_id': task.id,
            'message': 'Task started successfully'
        })

    return await _sync_logic()

@extend_schema(
    summary="API Root",
    description="BuildTracker API root endpoint - Health check for the API",
    responses={
        200: {
            'type': 'object',
            'properties': {
                'message': {'type': 'string', 'description': 'API status message'}
            }
        }
    }
)
def index(request):
    return JsonResponse({'message': 'BuildTracker API is running'})