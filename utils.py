from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework import status
from functools import wraps
import bleach
import re
import os
import logging

logger = logging.getLogger(__name__)

def handle_view_exception(e, source, workspace=None):
    
    import traceback
    stack_trace = traceback.format_exc()
    
    # Sanitize stack trace
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
        message=f"Error in {source}: {str(e)}",
        source=source,
        workspace=workspace,
        error_code=type(e).__name__,
        stack_trace=stack_trace
    )
    
    return Response(
        {'error': 'An internal error occurred. Please contact support if the problem persists.'}, 
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )

def sanitize_input(value, max_length=None):
    if not value:
        return ''

    cleaned = bleach.clean(str(value).strip(), tags=[], strip=True)

    if max_length:
        cleaned = cleaned[:max_length]

    return cleaned

def validate_username(username):
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, 'Username can only contain letters, numbers, and underscores'
    
    if len(username) < 3 or len(username) > 30:
        return False, 'Username must be 3-30 characters'
    
    sql_patterns = ['select', 'drop', 'delete', 'insert', 'update', 'union', '--', ';']
    if any(pattern in username.lower() for pattern in sql_patterns):
        return False, 'Invalid username format'
    
    return True, None

def validate_password(password):
    if len(password) < 8:
        return False, 'Password must be at least 8 characters'
    
    if not re.search(r'\d', password):
        return False, 'Password must contain at least one number'
        
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, 'Password must contain at least one special character'
    
    return True, None

def validate_email_format(email):
    try:
        validate_email(email)
        return True, None
    except ValidationError:
        return False, 'Invalid email format'

def validate_organization_name(name):
    if not name or len(name.strip()) < 2:
        return False, 'Organization name must be at least 2 characters'
    
    if len(name) > 100:
        return False, 'Organization name cannot exceed 100 characters'
    
    if not re.match(r'^[a-zA-Z0-9\s\-_\.]+$', name):
        return False, 'Organization name contains invalid characters'
    
    return True, None

class IsOrganizationOwner(BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.owner == request.user

class IsOrganizationMember(BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.members.filter(id=request.user.id).exists()

def organization_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not hasattr(request.user, 'organization_memberships') or not request.user.organization_memberships.exists():
            return Response(
                {'error': 'User must belong to an organization'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        return view_func(request, *args, **kwargs)
    return wrapper

def rate_limit_key(user_id, action):
    return f"rate_limit:{user_id}:{action}"

def validate_file_size(file, max_size_mb=10):
    if file.size > max_size_mb * 1024 * 1024:
        return False, f'File size cannot exceed {max_size_mb}MB'
    return True, None

def validate_file_type(file, allowed_types=None):
    if allowed_types is None:
        allowed_types = ['image/jpeg', 'image/png', 'image/gif']
    
    if file.content_type not in allowed_types:
        return False, f'File type not allowed. Allowed types: {allowed_types}'
    return True, None

def validate_file_extension(filename, allowed_extensions=None):
    forbidden_extensions = ['exe', 'py', 'php', 'sh', 'bat', 'js', 'msi', 'com']
    
    ext = os.path.splitext(filename)[1].lower().replace('.', '')
    
    if ext in forbidden_extensions:
        return False, f'File extension .{ext} is strictly prohibited for security reasons.'
    
    if allowed_extensions is None:
        allowed_extensions = [
            'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 
            'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'tiff',
            'zip', 'rar', '7z', 'tar', 'gz',
            'csv', 'txt', 'json', 'md', 'rtf',
            'mp4', 'mov', 'avi', 'webm', 'mp3', 'wav',
            'fig', 'sketch', 'psd', 'ai', 'eps', 'xd', 'sql'
        ]
    
    allowed_extensions = [e.lower() for e in allowed_extensions]
    
    if ext not in allowed_extensions:
        return False, f'File extension .{ext} is not allowed. Allowed: {", ".join(allowed_extensions)}'
    
    return True, None

def validate_file_security(file, max_size_mb=10, allowed_extensions=None):
    is_valid, error = validate_file_size(file, max_size_mb)
    if not is_valid:
        return False, error
    
    is_valid, error = validate_file_extension(file.name, allowed_extensions)
    if not is_valid:
        return False, error
        
    return True, None

def check_storage_limit(user, file_size):
    from organizations.user_org_views import calculate_user_storage_and_files, get_plan_limits
    storage_data = calculate_user_storage_and_files(user)
    limits = get_plan_limits(user.plan_type, user)
    file_size_mb = file_size / (1024 * 1024)
    invalidate_user_cache(user)
    return storage_data['storage_used_mb'] + file_size_mb <= limits['max_storage_mb']

def invalidate_user_cache(user):
    """Invalidate user usage cache"""
    from django.core.cache import cache
    cache_key = f'user_usage_{user.id}'
    cache.delete(cache_key)

def check_workspace_permission(user, workspace, required_roles=['Owner', 'Admin', 'Member']):
    """
    Check if a user has specific roles in a workspace.
    Uses a simple per-instance cache on the user object to avoid redundant DB queries.
    """
    if not user or not user.is_authenticated:
        return False
    
    if not hasattr(user, '_workspace_role_cache'):
        user._workspace_role_cache = {}
    
    workspace_id = str(workspace.id) if hasattr(workspace, 'id') else str(workspace)
    
    if workspace_id not in user._workspace_role_cache:
        from workspaces.models import WorkspaceMember
        try:
            member = WorkspaceMember.objects.get(workspace_id=workspace_id, user=user)
            user._workspace_role_cache[workspace_id] = member.role
        except WorkspaceMember.DoesNotExist:
            user._workspace_role_cache[workspace_id] = None
    
    role = user._workspace_role_cache.get(workspace_id)
    return role in required_roles if role else False

def is_resource_owner_or_admin(user, workspace, resource):
    creator = getattr(resource, 'created_by', getattr(resource, 'uploaded_by', getattr(resource, 'author', None)))
    if creator == user:
        return True
    
    return check_workspace_permission(user, workspace, required_roles=['Owner', 'Admin'])

def create_workspace_log(workspace, user, log_type, action, description, entity_type='', entity_id=None, metadata=None, severity='info', request=None):
    from logs.tasks import create_workspace_log_task
    
    ip_address = None
    user_agent = ''
    
    if request:
        ip_address = request.headers.get('x-forwarded-for', request.META.get('REMOTE_ADDR'))
        user_agent = request.headers.get('user-agent', '')
    
    workspace_id = workspace.id if workspace else None
    user_id = user.id if user else None
    
    create_workspace_log_task.delay(
        workspace_id,
        user_id,
        log_type,
        action,
        description,
        entity_type,
        entity_id,
        metadata or {},
        severity,
        ip_address,
        user_agent
    )

def create_audit_log(workspace, user, action, entity_type, entity_id=None, old_values=None, new_values=None, request=None):
    from logs.tasks import create_audit_log_task
    
    ip_address = None
    user_agent = ''
    session_id = ''
    
    if request:
        ip_address = request.headers.get('x-forwarded-for', request.META.get('REMOTE_ADDR'))
        user_agent = request.headers.get('user-agent', '')
        session_id = request.session.session_key or ''
    
    workspace_id = workspace.id if workspace else None
    user_id = user.id if user else None
    
    create_audit_log_task.delay(
        workspace_id,
        user_id,
        action,
        entity_type,
        entity_id,
        old_values or {},
        new_values or {},
        ip_address,
        user_agent,
        session_id
    )

def create_user_activity_log(user, activity_type, workspace=None, module='', endpoint='', duration_ms=None, metadata=None, request=None):
    from logs.tasks import create_user_activity_log_task
    
    ip_address = None
    user_agent = ''
    session_id = ''
    
    if request:
        ip_address = request.headers.get('x-forwarded-for', request.META.get('REMOTE_ADDR'))
        user_agent = request.headers.get('user-agent', '')
        session_id = request.session.session_key or ''
        if not endpoint:
            endpoint = request.path
    
    workspace_id = workspace.id if workspace else None
    user_id = user.id if user else None
    
    create_user_activity_log_task.delay(
        user_id,
        activity_type,
        workspace_id,
        module,
        endpoint,
        duration_ms,
        metadata or {},
        ip_address,
        user_agent,
        session_id
    )

def create_notification(user, workspace, action, description=None, note_type=None, severity='info', triggered_by=None):
    from notifications.tasks import create_notification_task
    
    user_id = user.id if user else None
    workspace_id = workspace.id if workspace else None
    triggered_by_id = triggered_by.id if triggered_by else None
    
    if user_id:
        create_notification_task.delay(
            user_id,
            workspace_id,
            action,
            description,
            note_type,
            severity,
            triggered_by_id
        )

def create_system_event_log(event_type, severity, message, source, workspace=None, error_code='', stack_trace='', metadata=None):
    from logs.tasks import create_system_event_log_task
    
    workspace_id = workspace.id if hasattr(workspace, 'id') else workspace
    
    create_system_event_log_task.delay(
        event_type,
        severity,
        message,
        source,
        workspace_id,
        error_code,
        stack_trace,
        metadata or {}
    )

from contextlib import contextmanager  # noqa: E402
import time  # noqa: E402
from django.core.cache import cache  # noqa: E402

@contextmanager
def cache_lock(lock_key, timeout=10, sleep_time=0.1):
    """
    Context manager to prevent cache stampedes.
    Tries to acquire a Redis lock for a given key.
    """
    acquired = False
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        # cache.add is atomic in Redis
        if cache.add(lock_key, 'lock', timeout):
            acquired = True
            break
        time.sleep(sleep_time)
        
    try:
        yield acquired
    finally:
        if acquired:
            cache.delete(lock_key)