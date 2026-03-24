from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework import status, permissions
from rest_framework.decorators import permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from itertools import chain

from tasks.models import Task
from wiki.models import WikiDocument
from integrations.models import Integration
from workspaces.models import Workspace, WorkspaceMember
from quicklinks.models import QuickLink, SharedQuickLink
from logs.models import WorkspaceLog
from notifications.models import Notification
from files.models import File, Folder
from utils import sanitize_input

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'PageSize'
    max_page_size = 100
    page_query_param = 'Page'

def check_workspace_permission(user, workspace, required_roles=['Owner', 'Admin', 'Member']):
    try:
        
        member = WorkspaceMember.objects.get(workspace=workspace, user=user)
        return member.role in required_roles
    except WorkspaceMember.DoesNotExist:
        return False

def get_user_workspaces(user):
    
    workspace_ids = WorkspaceMember.objects.filter(
        user=user
    ).values_list('workspace_id', flat=True)
    return Workspace.objects.filter(id__in=workspace_ids)

def search_tasks(search_key, workspaces, workspace_filter=None, milestone=None, sprint=None):
    queryset = Task.objects.filter(workspace__in=workspaces)
    
    if workspace_filter:
        queryset = queryset.filter(workspace=workspace_filter)
    
    if milestone:
        queryset = queryset.filter(milestone=milestone)
    
    if sprint:
        queryset = queryset.filter(sprint=sprint)
    
    if search_key:
        from django.contrib.postgres.search import SearchQuery
        query = Q(search_vector=SearchQuery(search_key))
        clean_key = search_key.lstrip('#')
        if clean_key.isdigit():
            query |= Q(ticket_number=int(clean_key))
        queryset = queryset.filter(query)
    
    results = []
    for task in queryset:
        results.append({
            'id': task.id,
            'title': task.task_name,
            'content': task.task_description or '',
            'type': 'task',
            'workspace_id': task.workspace.id,
            'workspace_name': task.workspace.name,
            'created_at': task.created_at,
            'updated_at': task.updated_at,
            'relevance_score': 1.0,
            'url': '/tasks'
        })
    
    return results

def search_wiki(search_key, workspaces, workspace_filter=None):
    queryset = WikiDocument.objects.filter(workspace__in=workspaces)
    
    if workspace_filter:
        queryset = queryset.filter(workspace=workspace_filter)
    
    if search_key:
        from django.contrib.postgres.search import SearchQuery
        queryset = queryset.filter(search_vector=SearchQuery(search_key))
    
    results = []
    for doc in queryset:
        desc = doc.document_description or ''
        results.append({
            'id': doc.id,
            'title': doc.document_title,
            'content': desc[:200] + '...' if len(desc) > 200 else desc,
            'type': 'wiki',
            'workspace_id': doc.workspace.id,
            'workspace_name': doc.workspace.name,
            'created_at': doc.created_at,
            'updated_at': doc.updated_at,
            'relevance_score': 1.0,
            'url': f'/wiki/{doc.id}'
        })
    
    return results

def search_integrations(search_key, workspaces, workspace_filter=None):
    queryset = Integration.objects.filter(workspace__in=workspaces)
    
    if workspace_filter:
        queryset = queryset.filter(workspace=workspace_filter)
    
    if search_key:
        queryset = queryset.filter(
            Q(name__icontains=search_key) |
            Q(description__icontains=search_key)
        )
    
    results = []
    for integration in queryset:
        results.append({
            'id': integration.id,
            'title': integration.name,
            'content': integration.description or '',
            'type': 'integration',
            'workspace_id': integration.workspace.id,
            'workspace_name': integration.workspace.name,
            'created_at': integration.created_at,
            'updated_at': integration.updated_at,
            'relevance_score': 1.0,
            'url': f'/integrations/{integration.id}'
        })
    
    return results

def search_team(search_key, workspaces, workspace_filter=None):
    queryset = WorkspaceMember.objects.filter(workspace__in=workspaces).select_related('user')
    
    if workspace_filter:
        queryset = queryset.filter(workspace=workspace_filter)
    
    if search_key:
        queryset = queryset.filter(
            Q(user__first_name__icontains=search_key) |
            Q(user__last_name__icontains=search_key) |
            Q(user__email__icontains=search_key) |
            Q(job_role__icontains=search_key) |
            Q(name__icontains=search_key)
        )
    
    results = []
    for member in queryset:
        first = member.user.first_name or ''
        last = member.user.last_name or ''
        full_name = f"{first} {last}".strip() or member.user.email.split('@')[0]
        results.append({
            'id': str(member.id),
            'title': full_name,
            'content': member.job_role or member.role,
            'type': 'team',
            'workspace_id': member.workspace.id,
            'workspace_name': member.workspace.name,
            'created_at': member.joined_at,
            'updated_at': member.joined_at,
            'relevance_score': 1.0,
            'url': '/team'
        })
    
    return results

def search_quicklinks(search_key, workspaces, workspace_filter=None):
    ql_queryset = QuickLink.objects.filter(workspace__in=workspaces)
    if workspace_filter:
        ql_queryset = ql_queryset.filter(workspace=workspace_filter)
    if search_key:
        ql_queryset = ql_queryset.filter(
            Q(title__icontains=search_key) |
            Q(url__icontains=search_key) |
            Q(category__icontains=search_key)
        )
    
    shared_queryset = SharedQuickLink.objects.filter(workspace__in=workspaces)
    if workspace_filter:
        shared_queryset = shared_queryset.filter(workspace=workspace_filter)
    if search_key:
        shared_queryset = shared_queryset.filter(
            Q(title__icontains=search_key) |
            Q(url__icontains=search_key) |
            Q(category__icontains=search_key) |
            Q(description__icontains=search_key)
        )
    
    results = []
    for ql in ql_queryset:
        results.append({
            'id': str(ql.id),
            'title': ql.title,
            'content': ql.url,
            'type': 'quicklink',
            'workspace_id': ql.workspace.id if ql.workspace else None,
            'workspace_name': ql.workspace.name if ql.workspace else '',
            'created_at': ql.created_at,
            'updated_at': ql.updated_at,
            'relevance_score': 1.0,
            'url': '/quick-links'
        })
    for sq in shared_queryset:
        results.append({
            'id': str(sq.id),
            'title': sq.title,
            'content': sq.description or sq.url,
            'type': 'quicklink',
            'workspace_id': sq.workspace.id,
            'workspace_name': sq.workspace.name,
            'created_at': sq.created_at,
            'updated_at': sq.updated_at,
            'relevance_score': 1.0,
            'url': '/quick-links'
        })
    
    return results

def search_logs(search_key, workspaces, workspace_filter=None):
    queryset = WorkspaceLog.objects.filter(workspace__in=workspaces)
    
    if workspace_filter:
        queryset = queryset.filter(workspace=workspace_filter)
    
    if search_key:
        from django.contrib.postgres.search import SearchQuery
        queryset = queryset.filter(search_vector=SearchQuery(search_key))
    
    queryset = queryset[:20]
    
    results = []
    for log in queryset:
        results.append({
            'id': str(log.id),
            'title': log.action,
            'content': log.description[:200] + '...' if len(log.description) > 200 else log.description,
            'type': 'log',
            'workspace_id': log.workspace.id,
            'workspace_name': log.workspace.name,
            'created_at': log.created_at,
            'updated_at': log.created_at,
            'relevance_score': 0.8,
            'url': '/activity-logs'
        })
    
    return results

def search_files(search_key, workspaces, workspace_filter=None):
    folder_qs = Folder.objects.filter(workspace__in=workspaces)
    if workspace_filter:
        folder_qs = folder_qs.filter(workspace=workspace_filter)
    if search_key:
        folder_qs = folder_qs.filter(Q(name__icontains=search_key))
    
    file_qs = File.objects.filter(workspace__in=workspaces)
    if workspace_filter:
        file_qs = file_qs.filter(workspace=workspace_filter)
    if search_key:
        file_qs = file_qs.filter(
            Q(file_name__icontains=search_key) |
            Q(file_type__icontains=search_key)
        )
    
    results = []
    for folder in folder_qs:
        results.append({
            'id': str(folder.id),
            'title': folder.name,
            'content': 'Folder',
            'type': 'file',
            'workspace_id': folder.workspace.id,
            'workspace_name': folder.workspace.name,
            'created_at': folder.created_at,
            'updated_at': folder.updated_at,
            'relevance_score': 0.9,
            'url': '/wiki'
        })
    for f in file_qs:
        results.append({
            'id': str(f.id),
            'title': f.file_name,
            'content': f'{f.file_type} file — {f.file_size} bytes',
            'type': 'file',
            'workspace_id': f.workspace.id if f.workspace else None,
            'workspace_name': f.workspace.name if f.workspace else '',
            'created_at': f.uploaded_at,
            'updated_at': f.uploaded_at,
            'relevance_score': 0.9,
            'url': '/wiki'
        })
    return results

def search_notifications(search_key, workspaces, workspace_filter=None):
    queryset = Notification.objects.filter(workspace__in=workspaces)
    
    if workspace_filter:
        queryset = queryset.filter(workspace=workspace_filter)
    
    if search_key:
        queryset = queryset.filter(
            Q(action__icontains=search_key) |
            Q(description__icontains=search_key)
        )
    
    queryset = queryset[:20]
    
    results = []
    for notif in queryset:
        results.append({
            'id': str(notif.id),
            'title': notif.action,
            'content': notif.description or '',
            'type': 'notification',
            'workspace_id': notif.workspace.id if notif.workspace else None,
            'workspace_name': notif.workspace.name if notif.workspace else '',
            'created_at': notif.created_at,
            'updated_at': notif.created_at,
            'relevance_score': 0.7,
            'url': '/notifications'
        })
    
    return results

@extend_schema(
    tags=["Search"],
    summary="Global Search",
    description="Search across all accessible content",
    parameters=[
        {'name': 'SearchKey', 'in': 'query', 'schema': {'type': 'string'}, 'required': True},
        {'name': 'PageSize', 'in': 'query', 'schema': {'type': 'integer', 'default': 20}},
        {'name': 'SortColumn', 'in': 'query', 'schema': {'type': 'string', 'default': 'relevance'}},
        {'name': 'Page', 'in': 'query', 'schema': {'type': 'integer', 'default': 1}},
    ],
    responses={200: {'description': 'Global search results'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def global_search(request):
    @sync_to_async
    def _sync_logic():
        search_key = request.GET.get('SearchKey')
        if not search_key:
            return Response({'error': 'SearchKey parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

        search_key = sanitize_input(search_key)
        workspaces = get_user_workspaces(request.user)

        task_results = search_tasks(search_key, workspaces)
        wiki_results = search_wiki(search_key, workspaces)
        integration_results = search_integrations(search_key, workspaces)
        team_results = search_team(search_key, workspaces)
        quicklink_results = search_quicklinks(search_key, workspaces)
        log_results = search_logs(search_key, workspaces)
        notification_results = search_notifications(search_key, workspaces)
        file_results = search_files(search_key, workspaces)

        all_results = list(chain(
            task_results, wiki_results, integration_results,
            team_results, quicklink_results, log_results, notification_results, file_results
        ))

        sort_column = request.GET.get('SortColumn', 'relevance')
        if sort_column == 'relevance':
            all_results.sort(key=lambda x: x['relevance_score'], reverse=True)
        elif sort_column == 'created_at':
            all_results.sort(key=lambda x: x['created_at'], reverse=True)
        elif sort_column == 'updated_at':
            all_results.sort(key=lambda x: x['updated_at'], reverse=True)


        page_size = int(request.GET.get('PageSize', 20))
        page = int(request.GET.get('Page', 1))

        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        paginated_results = all_results[start_index:end_index]

        total_count = len(all_results)
        total_pages = (total_count + page_size - 1) // page_size

        categories = {
            'tasks': len(task_results),
            'wiki': len(wiki_results),
            'integrations': len(integration_results),
            'team': len(team_results),
            'quicklinks': len(quicklink_results),
            'logs': len(log_results),
            'notifications': len(notification_results),
            'files': len(file_results)
        }

        return Response({
            'results': paginated_results,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_pages': total_pages,
                'total_count': total_count
            },
            'categories': categories
        })

    return await _sync_logic()

@extend_schema(
    tags=["Search"],
    summary="Workspace Search",
    description="Search within a specific workspace",
    parameters=[
        {'name': 'SearchKey', 'in': 'query', 'schema': {'type': 'string'}, 'required': True},
        {'name': 'Type', 'in': 'query', 'schema': {'type': 'string', 'enum': ['tasks', 'wiki', 'integrations']}},
        {'name': 'Milestone', 'in': 'query', 'schema': {'type': 'integer'}},
        {'name': 'Sprint', 'in': 'query', 'schema': {'type': 'integer'}},
        {'name': 'PageSize', 'in': 'query', 'schema': {'type': 'integer', 'default': 10}},
        {'name': 'Page', 'in': 'query', 'schema': {'type': 'integer', 'default': 1}},
    ],
    responses={200: {'description': 'Workspace search results'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def workspace_search(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        search_key = request.GET.get('SearchKey')
        if not search_key:
            return Response({'error': 'SearchKey parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

        search_key = sanitize_input(search_key)
        search_type = request.GET.get('Type')
        milestone = request.GET.get('Milestone')
        sprint = request.GET.get('Sprint')

        if milestone:
            try:
                milestone = int(milestone)
            except ValueError:
                milestone = None

        if sprint:
            try:
                sprint = int(sprint)
            except ValueError:
                sprint = None

        workspaces = [workspace]
        results = []

        if not search_type or search_type == 'tasks':
            results.extend(search_tasks(search_key, workspaces, workspace, milestone, sprint))

        if not search_type or search_type == 'wiki':
            results.extend(search_wiki(search_key, workspaces, workspace))

        if not search_type or search_type == 'integrations':
            results.extend(search_integrations(search_key, workspaces, workspace))

        if not search_type or search_type == 'team':
            results.extend(search_team(search_key, workspaces, workspace))

        if not search_type or search_type == 'quicklinks':
            results.extend(search_quicklinks(search_key, workspaces, workspace))

        if not search_type or search_type == 'logs':
            results.extend(search_logs(search_key, workspaces, workspace))

        if not search_type or search_type == 'notifications':
            results.extend(search_notifications(search_key, workspaces, workspace))

        if not search_type or search_type == 'files':
            results.extend(search_files(search_key, workspaces, workspace))

        results.sort(key=lambda x: x['relevance_score'], reverse=True)


        page_size = int(request.GET.get('PageSize', 10))
        page = int(request.GET.get('Page', 1))

        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        paginated_results = results[start_index:end_index]

        total_count = len(results)
        total_pages = (total_count + page_size - 1) // page_size

        suggestions = []
        if search_key and len(search_key) > 2:
            task_titles = Task.objects.filter(workspace=workspace).values_list('task_name', flat=True)[:10]
            wiki_titles = WikiDocument.objects.filter(workspace=workspace).values_list('document_title', flat=True)[:10]

            all_titles = list(task_titles) + list(wiki_titles)
            suggestions = [title for title in all_titles if search_key.lower() in title.lower() and title.lower() != search_key.lower()][:5]

        return Response({
            'results': paginated_results,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_pages': total_pages,
                'total_count': total_count
            },
            'suggestions': suggestions
        })
    return await _sync_logic()

