from celery import shared_task
from auth_func.models import CustomUser
from workspaces.models import Workspace


@shared_task
def create_module_access_task(user_id, workspace_id, module_name, session_duration, ip_address, user_agent):
    """Create a ModuleAccess record asynchronously.
    
    This task is called from APIUsageTrackingMiddleware to avoid
    synchronous DB writes in the request/response cycle.
    """
    from modules.models import ModuleAccess

    user = CustomUser.objects.filter(id=user_id).first() if user_id else None
    workspace = Workspace.objects.filter(id=workspace_id).first() if workspace_id else None

    if user:
        ModuleAccess.objects.create(
            user=user,
            workspace=workspace,
            module_name=module_name,
            session_duration=session_duration,
            ip_address=ip_address,
            user_agent=user_agent
        )
