from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework.decorators import permission_classes
from rest_framework.response import Response
from rest_framework import permissions
from drf_spectacular.utils import extend_schema
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


def health_check(request):
    """Lightweight health check for load balancer probes.

    IMPORTANT: This endpoint must NOT:
    - Require authentication
    - Hit the database
    - Use DRF serialization
    - Run through heavy middleware

    It should respond in < 1ms with a simple 200 OK.
    """
    return JsonResponse({'status': 'ok'}, status=200)


def health_check_deep(request):
    """Deep health check — verifies DB and Redis are reachable.

    Use this for monitoring/alerting dashboards (NOT the load balancer probe,
    as it may be slower than the shallow check above).
    Returns 200 if all systems ok, 503 if any dependency is down.
    """
    from django.db import connection
    checks = {}
    healthy = True

    # Database
    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        checks['database'] = 'ok'
    except Exception as exc:
        checks['database'] = str(exc)
        healthy = False

    # Cache / Redis
    try:
        cache.set('_health_probe', '1', timeout=5)
        assert cache.get('_health_probe') == '1'
        checks['cache'] = 'ok'
    except Exception as exc:
        checks['cache'] = str(exc)
        healthy = False

    status_code = 200 if healthy else 503
    return JsonResponse(
        {'status': 'ok' if healthy else 'degraded', 'checks': checks},
        status=status_code,
    )