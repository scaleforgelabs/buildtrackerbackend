from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework import status, permissions
from rest_framework.decorators import permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Count, Q
from django.utils import timezone

from .models import Task, Sprint
from workspaces.models import Workspace, WorkspaceMember
from utils import check_workspace_permission, create_workspace_log


def serialize_sprint(sprint):
    return {
        'id': str(sprint.id),
        'name': sprint.name,
        'goal': sprint.goal,
        'sprint_number': sprint.sprint_number,
        'start_date': sprint.start_date.isoformat(),
        'end_date': sprint.end_date.isoformat(),
        'status': sprint.status,
        'duration_weeks': sprint.duration_weeks,
        'created_by': sprint.created_by_id,
        'created_at': sprint.created_at.isoformat(),
        'updated_at': sprint.updated_at.isoformat(),
    }


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def sprint_list(request, workspaceId):
    def _sync():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'GET':
            sprints = Sprint.objects.filter(workspace=workspace)
            return Response({'data': [serialize_sprint(s) for s in sprints]})

        # POST - create sprint (Owner/Admin only)
        if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
            return Response({'error': 'Only owners and admins can create sprints'}, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        name = data.get('name', '').strip()
        if not name:
            return Response({'error': 'Sprint name is required'}, status=status.HTTP_400_BAD_REQUEST)

        start_date = data.get('start_date')
        end_date = data.get('end_date')
        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        # Auto-assign next sprint number
        last = Sprint.objects.filter(workspace=workspace).order_by('-sprint_number').first()
        sprint_number = (last.sprint_number + 1) if last else 1

        sprint = Sprint.objects.create(
            workspace=workspace,
            name=name,
            goal=data.get('goal', ''),
            sprint_number=sprint_number,
            start_date=start_date,
            end_date=end_date,
            duration_weeks=data.get('duration_weeks'),
            created_by=request.user,
        )
        create_workspace_log(workspace=workspace, user=request.user, action=f'Created Sprint {sprint_number}: {name}')
        return Response({'data': serialize_sprint(sprint)}, status=status.HTTP_201_CREATED)

    return sync_to_async(_sync)() if False else _sync()


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def sprint_detail(request, workspaceId, sprintId):
    def _sync():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        sprint = get_object_or_404(Sprint, id=sprintId, workspace=workspace)

        if request.method == 'GET':
            return Response({'data': serialize_sprint(sprint)})

        if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
            return Response({'error': 'Only owners and admins can modify sprints'}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'PUT':
            data = request.data
            if 'name' in data:
                sprint.name = data['name'].strip() or sprint.name
            if 'goal' in data:
                sprint.goal = data['goal']
            if 'start_date' in data:
                sprint.start_date = data['start_date']
            if 'end_date' in data:
                sprint.end_date = data['end_date']
            if 'duration_weeks' in data:
                sprint.duration_weeks = data['duration_weeks']
            sprint.save()
            return Response({'data': serialize_sprint(sprint)})

        if request.method == 'DELETE':
            if sprint.status == 'active':
                return Response({'error': 'Cannot delete an active sprint. Complete it first.'}, status=status.HTTP_400_BAD_REQUEST)
            sprint_number = sprint.sprint_number
            sprint.delete()
            # Unassign tasks that belonged to this sprint
            Task.objects.filter(workspace=workspace, sprint=sprint_number).update(sprint=None)
            return Response(status=status.HTTP_204_NO_CONTENT)

    return _sync()


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def sprint_publish(request, workspaceId, sprintId):
    def _sync():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
            return Response({'error': 'Only owners and admins can publish sprints'}, status=status.HTTP_403_FORBIDDEN)

        sprint = get_object_or_404(Sprint, id=sprintId, workspace=workspace)
        if sprint.status != 'planning':
            return Response({'error': 'Only sprints in planning status can be published'}, status=status.HTTP_400_BAD_REQUEST)

        # Only one active sprint at a time
        if Sprint.objects.filter(workspace=workspace, status='active').exists():
            return Response({'error': 'A sprint is already active in this workspace'}, status=status.HTTP_400_BAD_REQUEST)

        sprint.status = 'active'
        sprint.save()
        create_workspace_log(workspace=workspace, user=request.user, action=f'Published Sprint {sprint.sprint_number}: {sprint.name}')
        return Response({'data': serialize_sprint(sprint)})

    return _sync()


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def sprint_complete(request, workspaceId, sprintId):
    def _sync():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
            return Response({'error': 'Only owners and admins can complete sprints'}, status=status.HTTP_403_FORBIDDEN)

        sprint = get_object_or_404(Sprint, id=sprintId, workspace=workspace)
        if sprint.status != 'active':
            return Response({'error': 'Only active sprints can be completed'}, status=status.HTTP_400_BAD_REQUEST)

        sprint.status = 'completed'
        sprint.save()
        create_workspace_log(workspace=workspace, user=request.user, action=f'Completed Sprint {sprint.sprint_number}: {sprint.name}')
        return Response({'data': serialize_sprint(sprint)})

    return _sync()


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def sprint_tasks(request, workspaceId, sprintId):
    def _sync():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        sprint = get_object_or_404(Sprint, id=sprintId, workspace=workspace)
        tasks = Task.objects.filter(workspace=workspace, sprint=sprint.sprint_number).select_related('assigned_to', 'created_by')

        from .serializers import TaskListSerializer
        return Response({'data': TaskListSerializer(tasks, many=True).data})

    return _sync()


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def backlog_tasks(request, workspaceId):
    """Tasks with no sprint assigned (backlog)."""
    def _sync():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        tasks = Task.objects.filter(
            workspace=workspace, sprint__isnull=True
        ).exclude(status='completed').select_related('assigned_to', 'created_by')

        from .serializers import TaskListSerializer
        return Response({'data': TaskListSerializer(tasks, many=True).data})

    return _sync()


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def assign_tasks_to_sprint(request, workspaceId, sprintId):
    """Bulk-assign tasks to a sprint."""
    def _sync():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
            return Response({'error': 'Only owners and admins can assign tasks to sprints'}, status=status.HTTP_403_FORBIDDEN)

        sprint = get_object_or_404(Sprint, id=sprintId, workspace=workspace)
        task_ids = request.data.get('task_ids', [])
        if not isinstance(task_ids, list):
            return Response({'error': 'task_ids must be a list'}, status=status.HTTP_400_BAD_REQUEST)

        updated = Task.objects.filter(workspace=workspace, id__in=task_ids).update(sprint=sprint.sprint_number)
        return Response({'updated': updated})

    return _sync()


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def remove_task_from_sprint(request, workspaceId, taskId):
    """Remove a task from its sprint (move to backlog)."""
    def _sync():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        task = get_object_or_404(Task, id=taskId, workspace=workspace)
        task.sprint = None
        task.save(update_fields=['sprint'])
        return Response({'success': True})

    return _sync()


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def sprint_velocity(request, workspaceId):
    """Velocity chart: story points completed per sprint."""
    def _sync():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        sprints = Sprint.objects.filter(workspace=workspace).order_by('sprint_number')
        result = []
        for sprint in sprints:
            tasks = Task.objects.filter(workspace=workspace, sprint=sprint.sprint_number)
            total_points = tasks.aggregate(total=Sum('story_points'))['total'] or 0
            completed_points = tasks.filter(status='completed').aggregate(total=Sum('story_points'))['total'] or 0
            total_tasks = tasks.count()
            completed_tasks = tasks.filter(status='completed').count()
            result.append({
                'sprint_id': str(sprint.id),
                'sprint_number': sprint.sprint_number,
                'name': sprint.name,
                'status': sprint.status,
                'start_date': sprint.start_date.isoformat(),
                'end_date': sprint.end_date.isoformat(),
                'total_points': total_points,
                'completed_points': completed_points,
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks,
                'velocity': completed_points,
            })
        return Response({'data': result})

    return _sync()
