from functools import wraps
from django.core.cache import cache
from django.http import JsonResponse
from rest_framework import status


# Error code constants
ERROR_CODES = {
    'INSUFFICIENT_PERMISSIONS': {
        'status': 403,
        'message': 'Insufficient permissions for this operation'
    },
    'RESOURCE_LOCKED': {
        'status': 423,
        'message': 'Resource is currently being processed'
    },
    'STORAGE_FULL': {
        'status': 507,
        'message': 'Storage quota exceeded'
    },
    'RATE_LIMIT_EXCEEDED': {
        'status': 429,
        'message': 'Rate limit exceeded. Please try again later'
    }
}


def get_error_response(code, custom_message=None):
    """Generate standardized error response"""
    error_info = ERROR_CODES.get(code, {'status': 500, 'message': 'Internal server error'})
    return JsonResponse(
        {
            'error': custom_message or error_info['message'],
            'code': code
        },
        status=error_info['status']
    )


from asgiref.sync import iscoroutinefunction

def rate_limit(requests_per_minute=60):
    """
    Rate limiting decorator
    Usage: @rate_limit(requests_per_minute=50)
    """
    def decorator(view_func):
        is_async = iscoroutinefunction(view_func)

        if is_async:
            @wraps(view_func)
            async def async_wrapper(request, *args, **kwargs):
                if hasattr(request, 'user') and request.user.is_authenticated:
                    user_id = str(request.user.id)
                else:
                    user_id = request.META.get('REMOTE_ADDR', 'unknown')
                
                module_path = f"{view_func.__module__}.{view_func.__name__}"
                cache_key = f"rate_limit:{module_path}:{user_id}"
                
                try:
                    request_count = cache.get(cache_key, 0)
                    
                    if request_count >= requests_per_minute:
                        return get_error_response(
                            'RATE_LIMIT_EXCEEDED',
                            f'Rate limit of {requests_per_minute} requests per minute exceeded'
                        )
                    
                    new_count = cache.incr(cache_key)
                    if new_count == 1:
                        cache.expire(cache_key, 60)
                except (ValueError, Exception):
                    cache.set(cache_key, 1, 60)
                
                return await view_func(request, *args, **kwargs)
            return async_wrapper

        else:
            @wraps(view_func)
            def sync_wrapper(request, *args, **kwargs):
                if hasattr(request, 'user') and request.user.is_authenticated:
                    user_id = str(request.user.id)
                else:
                    user_id = request.META.get('REMOTE_ADDR', 'unknown')
                
                module_path = f"{view_func.__module__}.{view_func.__name__}"
                cache_key = f"rate_limit:{module_path}:{user_id}"
                
                try:
                    request_count = cache.get(cache_key, 0)
                    
                    if request_count >= requests_per_minute:
                        return get_error_response(
                            'RATE_LIMIT_EXCEEDED',
                            f'Rate limit of {requests_per_minute} requests per minute exceeded'
                        )
                    
                    new_count = cache.incr(cache_key)
                    if new_count == 1:
                        cache.expire(cache_key, 60)
                except (ValueError, Exception):
                    cache.set(cache_key, 1, 60)
                
                return view_func(request, *args, **kwargs)
            return sync_wrapper

    return decorator


def admin_only(view_func):
    """Decorator to restrict access to admin users only"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return get_error_response('INSUFFICIENT_PERMISSIONS', 'Authentication required')
        
        if not request.user.is_staff:
            return get_error_response('INSUFFICIENT_PERMISSIONS', 'Admin access required')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper
