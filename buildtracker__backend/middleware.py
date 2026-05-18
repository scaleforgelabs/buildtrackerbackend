import traceback
import time
from django.utils.deprecation import MiddlewareMixin
from utils import create_system_event_log, create_user_activity_log


class ExceptionLoggingMiddleware(MiddlewareMixin):
    """Middleware to log exceptions as system events"""
    
    def process_exception(self, request, exception):
        """Log all exceptions to SystemEventLog"""
        try:
            workspace_id = None
            if hasattr(request, 'resolver_match') and request.resolver_match:
                workspace_id = request.resolver_match.kwargs.get('workspaceId')
            
            error_type = type(exception).__name__
            error_message = str(exception)
            
            # Sanitize stack trace - remove sensitive environment variables or local variables if possible
            # For now, let's at least ensure we don't log extremely long traces that might contain sensitive data dumps
            stack_trace = traceback.format_exc()
            if len(stack_trace) > 10000:
                stack_trace = stack_trace[:5000] + "\n... [TRUNCATED FOR SECURITY] ...\n" + stack_trace[-5000:]
            
            # Simple sanitization filter for common sensitive keys in stack trace lines
            sanitized_lines = []
            sensitive_keys = ['password', 'secret', 'token', 'key', 'auth', 'social']
            for line in stack_trace.splitlines():
                if any(key in line.lower() for key in sensitive_keys) and '=' in line:
                    sanitized_lines.append(f"{line.split('=')[0]}= [REDACTED]")
                else:
                    sanitized_lines.append(line)
            stack_trace = "\n".join(sanitized_lines)
            
            create_system_event_log(
                event_type='error',
                severity='error',
                message=f"{error_type}: {error_message}",
                source=request.path,
                workspace=workspace_id,
                error_code=error_type,
                stack_trace=stack_trace,
                metadata={
                    'method': request.method,
                    'user': str(request.user) if hasattr(request, 'user') else 'Anonymous',
                    'ip_address': request.headers.get('x-forwarded-for', request.META.get('REMOTE_ADDR')),
                    'user_agent': request.headers.get('user-agent', '')
                }
            )
        except Exception as log_error:
            # Don't let logging errors break the application
            print(f"Error logging exception: {log_error}")
        
        # Return None to let Django's default exception handling continue
        return None


class APIUsageTrackingMiddleware(MiddlewareMixin):
    """Middleware to track API usage patterns.
    
    PERFORMANCE NOTE: This middleware must NEVER perform synchronous DB reads or writes.
    All persistence is delegated to Celery tasks to avoid blocking the request cycle.
    """
    
    def process_request(self, request):
        """Record request start time"""
        request._start_time = time.time()
        return None
    
    def process_response(self, request, response):
        """Log API usage after response — all DB work is offloaded to Celery tasks"""
        try:
            if hasattr(request, 'user') and request.user.is_authenticated:
                duration_ms = None
                if hasattr(request, '_start_time'):
                    duration_ms = int((time.time() - request._start_time) * 1000)
                
                # Extract workspace_id from URL kwargs WITHOUT hitting the database.
                # The Celery task will resolve the Workspace object if needed.
                workspace_id = None
                if hasattr(request, 'resolver_match') and request.resolver_match:
                    workspace_id = request.resolver_match.kwargs.get('workspaceId')
                
                # Determine module from path
                module = 'unknown'
                path = request.path
                if '/tasks/' in path:
                    module = 'tasks'
                elif '/workspaces/' in path and '/members' not in path:
                    module = 'workspaces'
                elif '/members' in path or '/team' in path:
                    module = 'team'
                elif '/wiki/' in path:
                    module = 'wiki'
                elif '/integrations/' in path:
                    module = 'integrations'
                elif '/reports/' in path:
                    module = 'reports'
                elif '/monitoring/' in path or '/system/' in path:
                    module = 'monitoring'
                elif '/logs/' in path:
                    module = 'logs'
                elif '/module' in path:
                    module = 'modules'
                elif '/dashboard' in path or path == '/api/' or path == '/api':
                    module = 'dashboard'
                
                # Sanitize query params
                query_params = dict(request.GET)
                sensitive_keys = ['password', 'token', 'secret', 'key', 'auth', 'id_token', 'refresh_token']
                for key in list(query_params.keys()):
                    if any(sk in key.lower() for sk in sensitive_keys):
                        query_params[key] = '[REDACTED]'
                
                # Extract request metadata once (no DB calls)
                ip_address = request.headers.get('x-forwarded-for', request.META.get('REMOTE_ADDR'))
                user_agent = request.headers.get('user-agent', '')

                # Delegate activity logging to Celery (already uses .delay() internally)
                create_user_activity_log(
                    user=request.user,
                    activity_type='api_request',
                    workspace=None,  # Pass None — the task resolves workspace from workspace_id
                    module=module,
                    endpoint=request.path,
                    duration_ms=duration_ms,
                    metadata={
                        'method': request.method,
                        'status_code': response.status_code,
                        'query_params': query_params,
                        'workspace_id': str(workspace_id) if workspace_id else None
                    },
                    request=request
                )
                
                # Delegate ModuleAccess creation to a Celery task instead of synchronous DB write
                if module != 'unknown' and request.method == 'GET':
                    from modules.tasks import create_module_access_task
                    create_module_access_task.delay(
                        user_id=str(request.user.id),
                        workspace_id=str(workspace_id) if workspace_id else None,
                        module_name=module,
                        session_duration=duration_ms // 1000 if duration_ms else 0,
                        ip_address=ip_address,
                        user_agent=user_agent
                    )
        except Exception as log_error:
            # Don't let logging errors break the application
            print(f"Error logging API usage: {log_error}")
        
        return response

import contextvars  # noqa: E402
from django.db.backends.utils import CursorWrapper  # noqa: E402
from asgiref.sync import iscoroutinefunction  # noqa: E402

# Global context var to track queries per request regardless of threads
query_count_var = contextvars.ContextVar('query_count', default=0)

# Monkey-patch Django's CursorWrapper to globally count queries across ASGI thread boundaries
if not hasattr(CursorWrapper, '_patched_for_counting'):
    original_execute = CursorWrapper.execute
    original_executemany = CursorWrapper.executemany

    def patched_execute(self, sql, params=None):
        try:
            query_count_var.set(query_count_var.get() + 1)
        except LookupError:
            pass
        return original_execute(self, sql, params)

    def patched_executemany(self, sql, param_list):
        try:
            query_count_var.set(query_count_var.get() + 1)
        except LookupError:
            pass
        return original_executemany(self, sql, param_list)

    CursorWrapper.execute = patched_execute
    CursorWrapper.executemany = patched_executemany
    CursorWrapper._patched_for_counting = True


from django.utils.decorators import sync_and_async_middleware  # noqa: E402
import logging as _logging  # noqa: E402

_perf_logger = _logging.getLogger('buildtracker.performance')

@sync_and_async_middleware
def QueryAndTimingMiddleware(get_response):
    """
    Middleware to intercept every request, track execution time, and count DB queries.
    Prints the result strictly to the terminal for debugging purposes.
    """
    # Initialize the middleware flag
    if iscoroutinefunction(get_response):
        async def middleware(request):
            start_time = time.time()
            token = query_count_var.set(0)
            try:
                response = await get_response(request)
                return response
            finally:
                duration = time.time() - start_time
                queries = query_count_var.get()
                status_code = getattr(response, 'status_code', 'Unknown') if 'response' in locals() else 'Error'
                _perf_logger.info(
                    "[ENDPOINT] %s %s [%s] | Time: %.4fs | DB Queries: %d",
                    request.method, request.path, status_code, duration, queries
                )
                query_count_var.reset(token)
        return middleware
    else:
        def middleware(request):
            start_time = time.time()
            token = query_count_var.set(0)
            try:
                response = get_response(request)
                return response
            finally:
                duration = time.time() - start_time
                queries = query_count_var.get()
                status_code = getattr(response, 'status_code', 'Unknown') if 'response' in locals() else 'Error'
                _perf_logger.info(
                    "[ENDPOINT] %s %s [%s] | Time: %.4fs | DB Queries: %d",
                    request.method, request.path, status_code, duration, queries
                )
                query_count_var.reset(token)
        return middleware
