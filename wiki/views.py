from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework import status, permissions
from rest_framework.decorators import permission_classes, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from django.utils.html import escape
from cachalot.api import cachalot_disabled


from .models import WikiDocument, WikiDocumentAttachment
from .serializers import WikiDocumentSerializer, WikiDocumentCreateSerializer, WikiDocumentAttachmentSerializer, UserSerializer
from workspaces.models import Workspace
from utils import sanitize_input, check_storage_limit, check_workspace_permission, create_workspace_log, create_audit_log, create_user_activity_log, is_resource_owner_or_admin

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'PageSize'
    max_page_size = 100
    page_query_param = 'Page'

def get_filtered_documents(queryset, request):
    search_key = request.GET.get('SearchKey')
    visibility = request.GET.get('Visibility')
    category = request.GET.get('Category')
    sort_column = request.GET.get('SortColumn', 'updated_at')
    sort_order = request.GET.get('SortOrder', 'desc')
    
    if search_key:
        search_key = sanitize_input(search_key)
        from django.contrib.postgres.search import SearchQuery
        queryset = queryset.filter(search_vector=SearchQuery(search_key))
    
    if visibility:
        queryset = queryset.filter(visibility=visibility)
    
    if category:
        queryset = queryset.filter(category__icontains=category)
    
    order_prefix = '-' if sort_order == 'desc' else ''
    queryset = queryset.order_by(f"{order_prefix}{sort_column}")
    
    return queryset

@extend_schema(
    tags=["Wiki"],
    summary="Wiki Documents",
    description="GET: List wiki documents with filtering. POST: Create new wiki document",
    parameters=[
        {'name': 'SearchKey', 'in': 'query', 'schema': {'type': 'string'}},
        {'name': 'Visibility', 'in': 'query', 'schema': {'type': 'string', 'enum': ['private', 'public']}},
        {'name': 'Category', 'in': 'query', 'schema': {'type': 'string'}},
        {'name': 'SortColumn', 'in': 'query', 'schema': {'type': 'string', 'default': 'updated_at'}},
        {'name': 'SortOrder', 'in': 'query', 'schema': {'type': 'string', 'enum': ['asc', 'desc'], 'default': 'desc'}},
        {'name': 'Page', 'in': 'query', 'schema': {'type': 'integer', 'default': 1}},
        {'name': 'PageSize', 'in': 'query', 'schema': {'type': 'integer', 'default': 20}},
    ],
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'document_title': {'type': 'string'},
                'document_description': {'type': 'string'},
                'category': {'type': 'string'},
                'visibility': {'type': 'string', 'enum': ['private', 'public']},
                'attachments': {'type': 'array', 'items': {'type': 'string'}}
            },
            'required': ['document_title', 'visibility']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'document_title': {'type': 'string'},
                'document_description': {'type': 'string'},
                'category': {'type': 'string'},
                'visibility': {'type': 'string', 'enum': ['private', 'public']},
                'attachments': {'type': 'array', 'items': {'type': 'string', 'format': 'binary'}}
            },
            'required': ['document_title', 'visibility']
        }
    },
    responses={
        200: {'description': 'List of wiki documents'},
        201: {'description': 'Wiki document created'}
    }
)
@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def wiki_documents(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'GET':
            create_user_activity_log(user=request.user, activity_type='api_request', workspace=workspace, module='wiki', request=request)

            with cachalot_disabled():
                documents = workspace.wiki_documents.all()
                filtered_documents = get_filtered_documents(documents, request)

                paginator = StandardResultsSetPagination()
                page = paginator.paginate_queryset(filtered_documents, request)

                serializer = WikiDocumentSerializer(page, many=True, context={'request': request})

            response = Response({
                'data': serializer.data,
                'pagination': {
                    'page': paginator.page.number,
                    'page_size': paginator.page_size,
                    'total_pages': paginator.page.paginator.num_pages,
                    'total_count': paginator.page.paginator.count
                },
                'filters': {
                    'search_key': request.GET.get('SearchKey', ''),
                    'visibility': request.GET.get('Visibility', ''),
                    'category': request.GET.get('Category', ''),
                    'sort_column': request.GET.get('SortColumn', 'updated_at'),
                    'sort_order': request.GET.get('SortOrder', 'desc')
                }
            })
            
            # Prevent caching at the browser/proxy level
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            return response

        elif request.method == 'POST':

            if hasattr(request, 'FILES') and request.FILES:
                total_size = sum(f.size for f in request.FILES.getlist('attachments'))
                if not check_storage_limit(request.user, total_size):
                    return Response({
                        'error': 'Storage limit exceeded',
                        'message': 'Upgrade your plan to upload more files'
                    }, status=status.HTTP_402_PAYMENT_REQUIRED)

            clean_data = {}
            for key, value in request.data.items():
                if key != 'attachments' and not hasattr(value, 'read'):
                    clean_data[key] = value

            serializer = WikiDocumentCreateSerializer(data=clean_data, context={'workspace': workspace, 'request': request})
            if serializer.is_valid():
                document = serializer.save()

                create_workspace_log(
                    workspace=workspace,
                    user=request.user,
                    log_type='wiki_create',
                    action='create',
                    description=f"Created wiki document: {document.document_title}",
                    entity_type='wiki',
                    entity_id=document.id,
                    metadata={'document_title': document.document_title, 'category': document.category},
                    request=request
                )

                create_audit_log(
                    workspace=workspace,
                    user=request.user,
                    action='create',
                    entity_type='wiki',
                    entity_id=document.id,
                    new_values={'document_title': document.document_title, 'category': document.category},
                    request=request
                )

                create_user_activity_log(user=request.user, activity_type='api_request', workspace=workspace, module='wiki', request=request)

                return Response({
                    'document': WikiDocumentSerializer(document, context={'request': request}).data
                }, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    return await _sync_logic()

@extend_schema(
    tags=["Wiki"],
    summary="Wiki Document Detail",
    description="GET: Get document details. PUT: Update document. DELETE: Delete document",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'document_title': {'type': 'string'},
                'document_description': {'type': 'string'},
                'category': {'type': 'string'},
                'visibility': {'type': 'string', 'enum': ['private', 'public']},
                'attachments': {'type': 'array', 'items': {'type': 'string'}}
            }
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'document_title': {'type': 'string'},
                'document_description': {'type': 'string'},
                'category': {'type': 'string'},
                'visibility': {'type': 'string', 'enum': ['private', 'public']},
                'attachments': {'type': 'array', 'items': {'type': 'string', 'format': 'binary'}}
            }
        }
    },
    responses={200: {'description': 'Document details'}}
)
@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def wiki_document_detail(request, workspaceId, id):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        document = get_object_or_404(WikiDocument, id=id, workspace=workspace)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'GET':
            create_user_activity_log(user=request.user, activity_type='api_request', workspace=workspace, module='wiki', request=request)

            serializer = WikiDocumentSerializer(document, context={'request': request})
            return Response({
                'document': serializer.data,
                'attachments': WikiDocumentAttachmentSerializer(document.attachments.all(), many=True, context={'request': request}).data,
                'author': UserSerializer(document.author).data
            })

        elif request.method == 'PUT':
            if not is_resource_owner_or_admin(request.user, workspace, document):
                return Response({'error': 'Permission denied: You do not have permission to edit this document'}, status=status.HTTP_403_FORBIDDEN)

            if hasattr(request, 'FILES') and request.FILES:
                total_size = sum(f.size for f in request.FILES.getlist('attachments'))
                if not check_storage_limit(request.user, total_size):
                    return Response({
                        'error': 'Storage limit exceeded',
                        'message': 'Upgrade your plan to upload more files'
                    }, status=status.HTTP_402_PAYMENT_REQUIRED)

                attachment_files = request.FILES.getlist('attachments')
                for attachment_file in attachment_files:
                    WikiDocumentAttachment.objects.create(
                        document=document,
                        file=attachment_file,
                        file_name=attachment_file.name,
                        uploaded_by=request.user
                    )


            update_data = {}
            for key, value in request.data.items():
                if value is not None and value != '':
                    update_data[key] = value

            serializer = WikiDocumentSerializer(document, data=update_data, partial=True)
            if serializer.is_valid():
                old_values = {k: getattr(document, k, None) for k in update_data.keys()}
                serializer.save()

                create_workspace_log(
                    workspace=workspace,
                    user=request.user,
                    log_type='wiki_update',
                    action='update',
                    description=f"Updated wiki document: {document.document_title}",
                    entity_type='wiki',
                    entity_id=document.id,
                    metadata={'document_title': document.document_title, 'updated_fields': list(update_data.keys())},
                    request=request
                )

                create_audit_log(
                    workspace=workspace,
                    user=request.user,
                    action='update',
                    entity_type='wiki',
                    entity_id=document.id,
                    old_values=old_values,
                    new_values=update_data,
                    request=request
                )

                create_user_activity_log(user=request.user, activity_type='api_request', workspace=workspace, module='wiki', request=request)

                return Response({'document': serializer.data})
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        elif request.method == 'DELETE':
            if not is_resource_owner_or_admin(request.user, workspace, document):
                return Response({'error': 'Permission denied: Only the document author or workspace admins can delete this document'}, status=status.HTTP_403_FORBIDDEN)
            document_title = document.document_title
            document_id = document.id
            old_values = {'document_title': document.document_title, 'category': document.category}
            document.delete()

            create_workspace_log(
                workspace=workspace,
                user=request.user,
                log_type='wiki_delete',
                action='delete',
                description=f"Deleted wiki document: {document_title}",
                entity_type='wiki',
                entity_id=document_id,
                metadata={'document_title': document_title},
                request=request
            )

            create_audit_log(
                workspace=workspace,
                user=request.user,
                action='delete',
                entity_type='wiki',
                entity_id=document_id,
                old_values=old_values,
                request=request
            )

            create_user_activity_log(user=request.user, activity_type='api_request', workspace=workspace, module='wiki', request=request)

            return Response({'message': 'Wiki document deleted successfully'})

    return await _sync_logic()

@extend_schema(
    tags=["Wiki"],
    summary="Wiki Search",
    description="Search wiki documents with highlighting",
    parameters=[
        {'name': 'SearchKey', 'in': 'query', 'schema': {'type': 'string'}},
        {'name': 'Category', 'in': 'query', 'schema': {'type': 'string'}},
        {'name': 'PageSize', 'in': 'query', 'schema': {'type': 'integer', 'default': 10}},
    ],
    responses={200: {'description': 'Search results with highlights'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def wiki_search(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        search_key = request.GET.get('SearchKey', '')
        category = request.GET.get('Category')
        page_size = int(request.GET.get('PageSize', 10))

        documents = workspace.wiki_documents.all()

        if search_key:
            search_key = sanitize_input(search_key)
            from django.contrib.postgres.search import SearchQuery
            documents = documents.filter(search_vector=SearchQuery(search_key))

        if category:
            documents = documents.filter(category__icontains=category)

        paginator = StandardResultsSetPagination()
        paginator.page_size = page_size
        page = paginator.paginate_queryset(documents, request)

        serializer = WikiDocumentSerializer(page, many=True, context={'request': request})


        highlights = []
        if search_key:
            escaped_key = escape(search_key)
            for doc in page:
                highlight = {}
                if search_key.lower() in doc.document_title.lower():
                    escaped_title = escape(doc.document_title)
                    highlight['title'] = escaped_title.replace(escaped_key, f"<mark>{escaped_key}</mark>")
                if doc.document_description and search_key.lower() in doc.document_description.lower():
                    escaped_desc = escape(doc.document_description)
                    highlight['description'] = escaped_desc.replace(escaped_key, f"<mark>{escaped_key}</mark>")
                if highlight:
                    highlight['document_id'] = str(doc.id)
                    highlights.append(highlight)

        return Response({
            'data': serializer.data,
            'pagination': {
                'page': paginator.page.number,
                'page_size': paginator.page_size,
                'total_pages': paginator.page.paginator.num_pages,
                'total_count': paginator.page.paginator.count
            },
            'highlights': highlights
        })
    return await _sync_logic()

