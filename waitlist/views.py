from adrf.decorators import api_view
from rest_framework.decorators import permission_classes, parser_classes
from rest_framework import status, permissions
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from asgiref.sync import sync_to_async

from .models import WaitlistEntry
from .serializers import WaitlistEntrySerializer, WaitlistCreateSerializer
from utils import sanitize_input

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'PageSize'
    max_page_size = 100
    page_query_param = 'Page'

def is_admin_user(user):
    """Check if user is a superuser/admin"""
    return user.is_authenticated and user.is_superuser

def get_filtered_waitlist(queryset, request):
    search_key = request.GET.get('SearchKey')
    
    if search_key:
        search_key = sanitize_input(search_key)
        queryset = queryset.filter(email__icontains=search_key)
    
    return queryset

@extend_schema(
    summary="Waitlist Management",
    description="POST: Add email to waitlist (public). GET: List waitlist entries (admin only)",
    parameters=[
        {'name': 'SearchKey', 'in': 'query', 'schema': {'type': 'string'}},
        {'name': 'Page', 'in': 'query', 'schema': {'type': 'integer', 'default': 1}},
        {'name': 'PageSize', 'in': 'query', 'schema': {'type': 'integer', 'default': 20}},
    ],
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'email': {'type': 'string', 'format': 'email'}
            },
            'required': ['email']
        },
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'email': {'type': 'string', 'format': 'email'}
            },
            'required': ['email']
        }
    },
    responses={
        200: {'description': 'Waitlist entries (GET only)'},
        201: {'description': 'Added to waitlist successfully (POST only)'},
        403: {'description': 'Admin access required (GET only)'}
    }
)
@api_view(['GET', 'POST'])
@parser_classes([JSONParser, MultiPartParser, FormParser])
async def waitlist(request):
    @sync_to_async
    def _sync_logic():
        if request.method == 'GET':
            # Admin only access for GET
            if not is_admin_user(request.user):
                return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)
            
            entries = WaitlistEntry.objects.all()
            filtered_entries = get_filtered_waitlist(entries, request)
            
            paginator = StandardResultsSetPagination()
            page = paginator.paginate_queryset(filtered_entries, request)
            
            serializer = WaitlistEntrySerializer(page, many=True)
            
            return Response({
                'data': serializer.data,
                'pagination': {
                    'page': paginator.page.number,
                    'page_size': paginator.page_size,
                    'total_pages': paginator.page.paginator.num_pages,
                    'total_count': paginator.page.paginator.count
                }
            })
        
        elif request.method == 'POST':
            # Public access for POST
            serializer = WaitlistCreateSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response({
                    'message': 'Added to waitlist successfully'
                }, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
    return await _sync_logic()