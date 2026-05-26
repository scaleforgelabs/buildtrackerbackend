import csv
import io
import uuid
from datetime import date, timedelta

from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.http import HttpResponse

from .models import GanttProject, GanttTask
from workspaces.models import Workspace
from utils import check_workspace_permission


# ─────────────────────────────────────────────
# Serialiser helpers
# ─────────────────────────────────────────────

def _ser_project(p):
    return {
        'id': str(p.id),
        'name': p.name,
        'description': p.description,
        'custom_field_schema': p.custom_field_schema or [],
        'created_by': p.created_by_id,
        'created_at': p.created_at.isoformat(),
        'updated_at': p.updated_at.isoformat(),
    }


def _ser_task(t):
    return {
        'id': str(t.id),
        'project': str(t.project_id),
        'name': t.name,
        'start_date': t.start_date.isoformat(),
        'end_date': t.end_date.isoformat(),
        'progress': t.progress,
        'task_type': t.task_type,
        'dependencies': t.dependencies or '',
        'assignee_id': str(t.assignee_id) if t.assignee_id else None,
        'assignee_name': (
            f"{t.assignee.first_name} {t.assignee.last_name}".strip() or t.assignee.email
            if t.assignee else None
        ),
        'notes': t.notes or '',
        'parent_task': str(t.parent_task_id) if t.parent_task_id else None,
        'display_order': t.display_order,
        'hide_children': t.hide_children,
        'estimated_cost': str(t.estimated_cost) if t.estimated_cost is not None else None,
        'actual_cost': str(t.actual_cost) if t.actual_cost is not None else None,
        'custom_fields': t.custom_fields or {},
    }


def _parse_date(value, fallback=None):
    """Try multiple common date formats."""
    if not value:
        return fallback or date.today()
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%m/%d/%y', '%d-%m-%Y'):
        try:
            from datetime import datetime
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return fallback or date.today()


# ─────────────────────────────────────────────
# Projects
# ─────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def gantt_projects(request, workspaceId):
    workspace = get_object_or_404(Workspace, id=workspaceId)
    if not check_workspace_permission(request.user, workspace):
        return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        projects = GanttProject.objects.filter(workspace=workspace)
        return Response({'data': [_ser_project(p) for p in projects]})

    if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
        return Response({'error': 'Only owners/admins can create projects'}, status=status.HTTP_403_FORBIDDEN)

    name = (request.data.get('name') or '').strip()
    if not name:
        return Response({'error': 'name is required'}, status=status.HTTP_400_BAD_REQUEST)

    project = GanttProject.objects.create(
        workspace=workspace,
        name=name,
        description=request.data.get('description', ''),
        created_by=request.user,
    )
    return Response({'data': _ser_project(project)}, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def gantt_project_detail(request, workspaceId, projectId):
    workspace = get_object_or_404(Workspace, id=workspaceId)
    if not check_workspace_permission(request.user, workspace):
        return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

    project = get_object_or_404(GanttProject, id=projectId, workspace=workspace)

    if request.method == 'GET':
        return Response({'data': _ser_project(project)})

    if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
        return Response({'error': 'Only owners/admins can modify projects'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'PUT':
        project.name = (request.data.get('name') or project.name).strip()
        project.description = request.data.get('description', project.description)
        if 'custom_field_schema' in request.data:
            project.custom_field_schema = request.data['custom_field_schema']
        project.save()
        return Response({'data': _ser_project(project)})

    project.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────
# Tasks (bulk list + create)
# ─────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def gantt_tasks(request, workspaceId, projectId):
    workspace = get_object_or_404(Workspace, id=workspaceId)
    if not check_workspace_permission(request.user, workspace):
        return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

    project = get_object_or_404(GanttProject, id=projectId, workspace=workspace)

    if request.method == 'GET':
        tasks = project.tasks.select_related('assignee')
        return Response({'data': [_ser_task(t) for t in tasks]})

    name = (request.data.get('name') or '').strip()
    if not name:
        return Response({'error': 'name is required'}, status=status.HTTP_400_BAD_REQUEST)

    # Auto-increment display_order
    last = project.tasks.order_by('-display_order').first()
    order = (last.display_order + 1) if last else 0

    ec = request.data.get('estimated_cost')
    ac = request.data.get('actual_cost')
    task = GanttTask.objects.create(
        project=project,
        name=name,
        start_date=_parse_date(request.data.get('start_date')),
        end_date=_parse_date(request.data.get('end_date')),
        progress=int(request.data.get('progress', 0)),
        task_type=request.data.get('task_type', 'task'),
        dependencies=request.data.get('dependencies', ''),
        assignee_id=request.data.get('assignee_id') or None,
        notes=request.data.get('notes', ''),
        parent_task_id=request.data.get('parent_task') or None,
        display_order=order,
        estimated_cost=ec if ec not in (None, '') else None,
        actual_cost=ac if ac not in (None, '') else None,
        custom_fields=request.data.get('custom_fields') or {},
    )
    return Response({'data': _ser_task(task)}, status=status.HTTP_201_CREATED)


@api_view(['PUT', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def gantt_task_detail(request, workspaceId, projectId, taskId):
    workspace = get_object_or_404(Workspace, id=workspaceId)
    if not check_workspace_permission(request.user, workspace):
        return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

    project = get_object_or_404(GanttProject, id=projectId, workspace=workspace)
    task = get_object_or_404(GanttTask, id=taskId, project=project)

    if request.method == 'DELETE':
        task.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # PUT
    data = request.data
    if 'name' in data:
        task.name = data['name'].strip() or task.name
    if 'start_date' in data:
        task.start_date = _parse_date(data['start_date'], task.start_date)
    if 'end_date' in data:
        task.end_date = _parse_date(data['end_date'], task.end_date)
    if 'progress' in data:
        task.progress = max(0, min(100, int(data['progress'])))
    if 'task_type' in data:
        task.task_type = data['task_type']
    if 'dependencies' in data:
        task.dependencies = data['dependencies']
    if 'assignee_id' in data:
        task.assignee_id = data['assignee_id'] or None
    if 'notes' in data:
        task.notes = data['notes']
    if 'parent_task' in data:
        task.parent_task_id = data['parent_task'] or None
    if 'display_order' in data:
        task.display_order = int(data['display_order'])
    if 'hide_children' in data:
        task.hide_children = bool(data['hide_children'])
    if 'estimated_cost' in data:
        task.estimated_cost = data['estimated_cost'] if data['estimated_cost'] not in (None, '') else None
    if 'actual_cost' in data:
        task.actual_cost = data['actual_cost'] if data['actual_cost'] not in (None, '') else None
    if 'custom_fields' in data:
        task.custom_fields = data['custom_fields'] or {}
    task.save()
    return Response({'data': _ser_task(task)})


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def gantt_bulk_update(request, workspaceId, projectId):
    """Bulk-update display_order + dates after drag-and-drop."""
    workspace = get_object_or_404(Workspace, id=workspaceId)
    if not check_workspace_permission(request.user, workspace):
        return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

    project = get_object_or_404(GanttProject, id=projectId, workspace=workspace)
    updates = request.data.get('updates', [])
    for upd in updates:
        task_id = upd.get('id')
        if not task_id:
            continue
        try:
            task = GanttTask.objects.get(id=task_id, project=project)
        except GanttTask.DoesNotExist:
            continue
        if 'start_date' in upd:
            task.start_date = _parse_date(upd['start_date'], task.start_date)
        if 'end_date' in upd:
            task.end_date = _parse_date(upd['end_date'], task.end_date)
        if 'progress' in upd:
            task.progress = max(0, min(100, int(upd['progress'])))
        if 'display_order' in upd:
            task.display_order = int(upd['display_order'])
        task.save(update_fields=['start_date', 'end_date', 'progress', 'display_order'])
    return Response({'updated': len(updates)})


# ─────────────────────────────────────────────
# CSV Import
# ─────────────────────────────────────────────

# MS Project column aliases → our field names
_COL_MAP = {
    'task name': 'name', 'name': 'name', 'task': 'name',
    'start': 'start_date', 'start date': 'start_date',
    'finish': 'end_date', 'end date': 'end_date', 'due date': 'end_date',
    '% complete': 'progress', 'percent complete': 'progress', 'progress': 'progress',
    'predecessors': 'dependencies', 'dependencies': 'dependencies',
    'resource names': 'assignee_name', 'assigned to': 'assignee_name',
    'notes': 'notes', 'description': 'notes',
    'type': 'task_type', 'task type': 'task_type',
    'estimated cost': 'estimated_cost', 'actual cost': 'actual_cost',
}

# Columns that are known but don't map to a field (ignore, not custom fields)
_SKIP_COLS = {
    'duration', 'wbs', 'outline number', 'outline level',
    'id', 'unique id', 'cost', 'baseline cost', 'baseline duration',
}


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def gantt_import(request, workspaceId, projectId):
    workspace = get_object_or_404(Workspace, id=workspaceId)
    if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
        return Response({'error': 'Only owners/admins can import'}, status=status.HTTP_403_FORBIDDEN)

    project = get_object_or_404(GanttProject, id=projectId, workspace=workspace)

    csv_file = request.FILES.get('file')
    if not csv_file:
        return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        content = csv_file.read().decode('utf-8-sig')  # handle BOM from MS Office
        reader = csv.DictReader(io.StringIO(content))
    except Exception as e:
        return Response({'error': f'Could not parse CSV: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

    last = project.tasks.order_by('-display_order').first()
    order = (last.display_order + 1) if last else 0
    created = 0

    # ── Detect custom-field columns from the CSV header ──────────────────
    # Any column that is not in _COL_MAP and not in _SKIP_COLS is treated
    # as a custom field.  We auto-add unknown ones to the project schema.
    schema = list(project.custom_field_schema or [])
    schema_by_name = {f['name'].lower(): f['id'] for f in schema}
    custom_col_names = []  # original-case column names that are custom fields

    for col in (reader.fieldnames or []):
        col_lower = col.strip().lower()
        if col_lower in _COL_MAP or col_lower in _SKIP_COLS or not col_lower:
            continue
        custom_col_names.append(col.strip())
        if col_lower not in schema_by_name:
            field_id = str(uuid.uuid4())
            schema.append({'id': field_id, 'name': col.strip(), 'type': 'text'})
            schema_by_name[col_lower] = field_id

    if custom_col_names:
        project.custom_field_schema = schema
        project.save(update_fields=['custom_field_schema'])

    # ── Import rows ───────────────────────────────────────────────────────
    for row in reader:
        normalised = {k.strip().lower(): v.strip() for k, v in row.items()}
        mapped = {}
        for col, value in normalised.items():
            field = _COL_MAP.get(col)
            if field and value:
                mapped[field] = value

        name = mapped.get('name', '').strip()
        if not name:
            continue

        start = _parse_date(mapped.get('start_date'))
        end = _parse_date(mapped.get('end_date'), start + timedelta(days=1))
        if end < start:
            end = start + timedelta(days=1)

        try:
            prog = int(float(mapped.get('progress', '0').replace('%', '')))
        except (ValueError, AttributeError):
            prog = 0

        # Collect custom field values for this row
        custom_fields = {}
        for col_name in custom_col_names:
            field_id = schema_by_name.get(col_name.lower())
            value = row.get(col_name, '').strip()
            if field_id and value:
                custom_fields[field_id] = value

        # Parse optional cost fields
        def _parse_decimal(v):
            try:
                return float(v.replace(',', '')) if v else None
            except ValueError:
                return None

        GanttTask.objects.create(
            project=project,
            name=name,
            start_date=start,
            end_date=end,
            progress=min(100, max(0, prog)),
            task_type=mapped.get('task_type', 'task').lower()
                if mapped.get('task_type', '').lower() in ('task', 'milestone', 'project')
                else 'task',
            dependencies=mapped.get('dependencies', ''),
            notes=mapped.get('notes', ''),
            estimated_cost=_parse_decimal(mapped.get('estimated_cost', '')),
            actual_cost=_parse_decimal(mapped.get('actual_cost', '')),
            custom_fields=custom_fields,
            display_order=order,
        )
        order += 1
        created += 1

    return Response({'created': created, 'custom_fields_added': len(custom_col_names)})


# ─────────────────────────────────────────────
# CSV Export
# ─────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def gantt_export(request, workspaceId, projectId):
    workspace = get_object_or_404(Workspace, id=workspaceId)
    if not check_workspace_permission(request.user, workspace):
        return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

    project = get_object_or_404(GanttProject, id=projectId, workspace=workspace)
    tasks = project.tasks.select_related('assignee').order_by('display_order')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{project.name}.csv"'
    response.write('\ufeff')  # BOM for MS Excel

    writer = csv.writer(response)
    # Build custom field header names from project schema
    schema = project.custom_field_schema or []
    custom_headers = [f['name'] for f in schema]

    writer.writerow([
        'Task Name', 'Type', 'Start', 'Finish', 'Duration', '% Complete',
        'Predecessors', 'Resource Names', 'Estimated Cost', 'Actual Cost', 'Notes',
        *custom_headers,
    ])

    for t in tasks:
        duration = (t.end_date - t.start_date).days
        assignee = ''
        if t.assignee:
            assignee = f"{t.assignee.first_name} {t.assignee.last_name}".strip() or t.assignee.email
        custom_values = [str((t.custom_fields or {}).get(f['id'], '')) for f in schema]
        writer.writerow([
            t.name,
            t.task_type.capitalize(),
            t.start_date.strftime('%Y-%m-%d'),
            t.end_date.strftime('%Y-%m-%d'),
            f'{duration}d',
            t.progress,
            t.dependencies or '',
            assignee,
            str(t.estimated_cost) if t.estimated_cost is not None else '',
            str(t.actual_cost) if t.actual_cost is not None else '',
            t.notes or '',
            *custom_values,
        ])

    return response
