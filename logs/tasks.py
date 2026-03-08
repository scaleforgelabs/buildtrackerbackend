from celery import shared_task
from .models import WorkspaceLog, AuditTrailLog, UserActivityLog, SystemEventLog
from workspaces.models import Workspace
from auth_func.models import CustomUser

@shared_task
def create_workspace_log_task(workspace_id, user_id, log_type, action, description, entity_type, entity_id, metadata, severity, ip_address, user_agent):
    workspace = Workspace.objects.filter(id=workspace_id).first() if workspace_id else None
    user = CustomUser.objects.filter(id=user_id).first() if user_id else None
    
    WorkspaceLog.objects.create(
        workspace=workspace,
        user=user,
        log_type=log_type,
        action=action,
        description=description,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata=metadata or {},
        severity=severity,
        ip_address=ip_address,
        user_agent=user_agent
    )

@shared_task
def create_audit_log_task(workspace_id, user_id, action, entity_type, entity_id, old_values, new_values, ip_address, user_agent, session_id):
    workspace = Workspace.objects.filter(id=workspace_id).first() if workspace_id else None
    user = CustomUser.objects.filter(id=user_id).first() if user_id else None
    
    AuditTrailLog.objects.create(
        workspace=workspace,
        user=user,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values=old_values or {},
        new_values=new_values or {},
        ip_address=ip_address,
        user_agent=user_agent,
        session_id=session_id
    )

@shared_task
def create_user_activity_log_task(user_id, activity_type, workspace_id, module, endpoint, duration_ms, metadata, ip_address, user_agent, session_id):
    workspace = Workspace.objects.filter(id=workspace_id).first() if workspace_id else None
    user = CustomUser.objects.filter(id=user_id).first() if user_id else None
    
    UserActivityLog.objects.create(
        user=user,
        workspace=workspace,
        activity_type=activity_type,
        module=module,
        endpoint=endpoint,
        duration_ms=duration_ms,
        metadata=metadata or {},
        ip_address=ip_address,
        user_agent=user_agent,
        session_id=session_id
    )

@shared_task
def create_system_event_log_task(event_type, severity, message, source, workspace_id, error_code, stack_trace, metadata):
    workspace = Workspace.objects.filter(id=workspace_id).first() if workspace_id else None
    
    SystemEventLog.objects.create(
        workspace=workspace,
        event_type=event_type,
        severity=severity,
        message=message,
        source=source,
        error_code=error_code,
        stack_trace=stack_trace,
        metadata=metadata or {}
    )
