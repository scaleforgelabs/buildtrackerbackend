from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework import status, permissions
from rest_framework.decorators import permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.http import Http404
from drf_spectacular.utils import extend_schema
from datetime import datetime

from .models import File, Folder
from .serializers import FileSerializer, FileUploadSerializer, FolderSerializer, FolderCreateSerializer
from workspaces.models import Workspace
from utils import sanitize_input, check_storage_limit, check_workspace_permission

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'PageSize'
    max_page_size = 100
    page_query_param = 'Page'

def get_filtered_files(queryset, request):
    search_key = request.GET.get('SearchKey')
    file_type = request.GET.get('FileType')
    date_from = request.GET.get('DateFrom')
    sort_column = request.GET.get('SortColumn', 'uploaded_at')
    sort_order = request.GET.get('SortOrder', 'desc')
    
    if search_key:
        search_key = sanitize_input(search_key)
        queryset = queryset.filter(file_name__icontains=search_key)
    
    if file_type:
        queryset = queryset.filter(file_type__iexact=file_type)
    
    if date_from:
        try:
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            queryset = queryset.filter(uploaded_at__date__gte=date_from)
        except ValueError:
            pass
    
    order_prefix = '-' if sort_order == 'desc' else ''
    queryset = queryset.order_by(f"{order_prefix}{sort_column}")
    
    return queryset

@extend_schema(
    tags=["Files"],
    summary="File Upload",
    description="Upload a file with storage limit validation",
    request={
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'file': {'type': 'string', 'format': 'binary'}
            },
            'required': ['file']
        }
    },
    responses={
        201: {'description': 'File uploaded successfully'},
        402: {'description': 'Storage limit exceeded'}
    }
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
async def file_upload(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        from django.core.cache import cache

        if 'file' not in request.FILES:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)


        workspace = get_object_or_404(Workspace, id=workspaceId)
        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        uploaded_file = request.FILES['file']


        if not check_storage_limit(request.user, uploaded_file.size):
            return Response({
                'error': 'Storage limit exceeded',
                'message': 'Upgrade your plan to upload more files'
            }, status=status.HTTP_402_PAYMENT_REQUIRED)

        serializer = FileUploadSerializer(data={'file': uploaded_file, 'folder': request.data.get('folder')}, context={'request': request, 'workspace': workspace})
        if serializer.is_valid():
            file_obj = serializer.save()


            cache_key = f'user_usage_{workspace.owner.id}'
            cache.delete(cache_key)

            return Response({
                'file': FileSerializer(file_obj, context={'request': request}).data,
                'upload_url': FileSerializer(file_obj, context={'request': request}).data.get('file_url')
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    return await _sync_logic()

@extend_schema(
    tags=["Files"],
    summary="File Detail",
    description="Get file details or update file",
    responses={200: {'description': 'File details'}}
)
@api_view(['GET', 'PUT'])
@permission_classes([permissions.IsAuthenticated])
async def file_detail(request, id):
    @sync_to_async
    def _sync_logic():
        try:
            file_obj = File.objects.get(id=id)


            if file_obj.workspace:
                if not check_workspace_permission(request.user, file_obj.workspace):
                    return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            elif file_obj.uploaded_by != request.user:
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

            if request.method == 'GET':

                serializer = FileSerializer(file_obj, context={'request': request})
                return Response({
                    'file': serializer.data,
                    'download_url': serializer.data.get('file_url')
                })

            elif request.method == 'PUT':

                if 'file_name' in request.data:
                    file_obj.file_name = request.data['file_name']
                    file_obj.save()
                serializer = FileSerializer(file_obj, context={'request': request})
                return Response(serializer.data)

        except File.DoesNotExist:
            raise Http404("File not found")

    return await _sync_logic()

@extend_schema(
    tags=["Files"],
    summary="File Delete",
    description="Delete a file",
    responses={200: {'description': 'File deleted successfully'}}
)
@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
async def file_delete(request, id):
    @sync_to_async
    def _sync_logic():
        try:
            file_obj = File.objects.get(id=id)


            if file_obj.workspace:
                if not check_workspace_permission(request.user, file_obj.workspace, ['Owner', 'Admin']):
                    return Response({'error': 'Only workspace owners and admins can delete files'}, status=status.HTTP_403_FORBIDDEN)
            elif file_obj.uploaded_by != request.user:
                return Response({'error': 'Only file owner can delete this file'}, status=status.HTTP_403_FORBIDDEN)

            file_obj.delete()
            return Response({'message': 'File deleted successfully'})

        except File.DoesNotExist:
            return Response({'error': 'File not found'}, status=status.HTTP_404_NOT_FOUND)

    return await _sync_logic()

@extend_schema(
    tags=["Files"],
    summary="Workspace Files",
    description="List files in a workspace with filtering",
    parameters=[
        {'name': 'SearchKey', 'in': 'query', 'schema': {'type': 'string'}},
        {'name': 'FileType', 'in': 'query', 'schema': {'type': 'string'}},
        {'name': 'DateFrom', 'in': 'query', 'schema': {'type': 'string', 'format': 'date'}},
        {'name': 'SortColumn', 'in': 'query', 'schema': {'type': 'string', 'default': 'uploaded_at'}},
        {'name': 'SortOrder', 'in': 'query', 'schema': {'type': 'string', 'enum': ['asc', 'desc'], 'default': 'desc'}},
        {'name': 'Page', 'in': 'query', 'schema': {'type': 'integer', 'default': 1}},
        {'name': 'PageSize', 'in': 'query', 'schema': {'type': 'integer', 'default': 20}},
    ],
    responses={200: {'description': 'List of workspace files'}}
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
async def workspace_files(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied: You must be a member of this workspace'}, status=status.HTTP_403_FORBIDDEN)

        files = workspace.files.all()
        filtered_files = get_filtered_files(files, request)

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(filtered_files, request)

        serializer = FileSerializer(page, many=True, context={'request': request})

        return Response({
            'data': serializer.data,
            'pagination': {
                'page': paginator.page.number,
                'page_size': paginator.page_size,
                'total_pages': paginator.page.paginator.num_pages,
                'total_count': paginator.page.paginator.count
            },
            'filters': {
                'search_key': request.GET.get('SearchKey', ''),
                'file_type': request.GET.get('FileType', ''),
                'date_from': request.GET.get('DateFrom', ''),
                'sort_column': request.GET.get('SortColumn', 'uploaded_at'),
                'sort_order': request.GET.get('SortOrder', 'desc')
            }
        })

    return await _sync_logic()

@extend_schema(
    tags=["Files"],
    summary="Create Folder",
    description="Create a new folder in workspace",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string'},
                'parent': {'type': 'string', 'format': 'uuid'}
            },
            'required': ['name']
        }
    },
    responses={201: {'description': 'Folder created successfully'}}
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
async def create_folder(request, workspaceId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        serializer = FolderCreateSerializer(data=request.data, context={'request': request, 'workspace': workspace})
        if serializer.is_valid():
            folder = serializer.save()
            return Response(FolderSerializer(folder, context={'request': request}).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    return await _sync_logic()

@extend_schema(
    tags=["Files"],
    summary="Folder Contents",
    description="Get subfolders and files in a folder, or update folder",
    responses={200: {'description': 'Folder contents'}}
)
@api_view(['GET', 'PUT'])
@permission_classes([permissions.IsAuthenticated])
async def folder_contents(request, workspaceId, folderId=None):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'PUT' and folderId:

            folder = get_object_or_404(Folder, id=folderId, workspace=workspace)
            if 'folder_name' in request.data:
                folder.name = request.data['folder_name']
                folder.save()
            return Response(FolderSerializer(folder, context={'request': request}).data)


        folder = None
        if folderId:
            folder = get_object_or_404(Folder, id=folderId, workspace=workspace)

        folders = Folder.objects.filter(workspace=workspace, parent=folder)
        files = File.objects.filter(workspace=workspace, folder=folder)

        return Response({
            'folders': FolderSerializer(folders, many=True, context={'request': request}).data,
            'files': FileSerializer(files, many=True, context={'request': request}).data
        })

    return await _sync_logic()

@extend_schema(
    tags=["Files"],
    summary="Upload to Folder",
    description="Upload a file directly to a folder",
    request={
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'file': {'type': 'string', 'format': 'binary'}
            },
            'required': ['file']
        }
    },
    responses={201: {'description': 'File uploaded to folder successfully'}}
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
async def upload_to_folder(request, workspaceId, folderId):
    @sync_to_async
    def _sync_logic():
        from django.core.cache import cache

        if 'file' not in request.FILES:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        workspace = get_object_or_404(Workspace, id=workspaceId)
        folder = get_object_or_404(Folder, id=folderId, workspace=workspace)

        if not check_workspace_permission(request.user, workspace):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        uploaded_file = request.FILES['file']

        if not check_storage_limit(request.user, uploaded_file.size):
            return Response({
                'error': 'Storage limit exceeded',
                'message': 'Upgrade your plan to upload more files'
            }, status=status.HTTP_402_PAYMENT_REQUIRED)

        serializer = FileUploadSerializer(data={'file': uploaded_file, 'folder': folder.id}, context={'request': request, 'workspace': workspace})
        if serializer.is_valid():
            file_obj = serializer.save()
            cache_key = f'user_usage_{workspace.owner.id}'
            cache.delete(cache_key)
            return Response(FileSerializer(file_obj, context={'request': request}).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    return await _sync_logic()

@extend_schema(
    tags=["Files"],
    summary="Delete Folder",
    description="Delete a folder and its contents",
    responses={200: {'description': 'Folder deleted successfully'}}
)
@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
async def delete_folder(request, workspaceId, folderId):
    @sync_to_async
    def _sync_logic():
        workspace = get_object_or_404(Workspace, id=workspaceId)
        if not check_workspace_permission(request.user, workspace, ['Owner', 'Admin']):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        folder = get_object_or_404(Folder, id=folderId, workspace=workspace)
        folder.delete()
        return Response({'message': 'Folder deleted successfully'})
    return await _sync_logic()

