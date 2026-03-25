from rest_framework import serializers
from .models import File, Folder
from django.contrib.auth import get_user_model

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'avatar']

class FolderSerializer(serializers.ModelSerializer):
    created_by_user = UserSerializer(source='created_by', read_only=True)
    path = serializers.SerializerMethodField()
    total_size = serializers.SerializerMethodField()
    contributors = UserSerializer(source='get_contributors', many=True, read_only=True)
    
    class Meta:
        model = Folder
        fields = ['id', 'name', 'parent', 'path', 'created_by', 'created_by_user', 'created_at', 'total_size', 'contributors']
        read_only_fields = ['created_by', 'created_at']
    
    def get_path(self, obj):
        return obj.get_path()

    def get_total_size(self, obj):
        return obj.get_total_size()

class FileSerializer(serializers.ModelSerializer):
    uploaded_by_user = UserSerializer(source='uploaded_by', read_only=True)
    file_url = serializers.SerializerMethodField()
    path = serializers.SerializerMethodField()
    
    class Meta:
        model = File
        fields = ['id', 'file_name', 'file_type', 'file_size', 'file_url', 'folder', 'path', 'uploaded_by', 'uploaded_by_user', 'uploaded_at']
        read_only_fields = ['uploaded_by', 'uploaded_at', 'file_size', 'file_type']
    
    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None
    
    def get_path(self, obj):
        return obj.get_path()

class FileUploadSerializer(serializers.ModelSerializer):
    file = serializers.FileField()
    folder = serializers.UUIDField(required=False, allow_null=True)
    
    class Meta:
        model = File
        fields = ['file', 'folder']
    
    def create(self, validated_data):
        from utils import invalidate_user_cache, validate_file_security
        
        user = self.context['request'].user
        workspace = self.context.get('workspace')
        folder_id = validated_data.pop('folder', None)
        file = validated_data['file']
        
        # Security Validation
        is_valid, error = validate_file_security(file)
        if not is_valid:
            raise serializers.ValidationError({'file': error})
        
        folder = None
        if folder_id:
            try:
                folder = Folder.objects.get(id=folder_id, workspace=workspace)
            except Folder.DoesNotExist:
                raise serializers.ValidationError({'folder': 'Invalid folder'})
        
        file_obj = File.objects.create(
            file=validated_data['file'],
            uploaded_by=user,
            workspace=workspace,
            folder=folder
        )
        
        if workspace and workspace.owner:
            invalidate_user_cache(workspace.owner)
        
        return file_obj

class FolderCreateSerializer(serializers.ModelSerializer):
    parent = serializers.UUIDField(required=False, allow_null=True)
    
    class Meta:
        model = Folder
        fields = ['name', 'parent']
    
    def create(self, validated_data):
        user = self.context['request'].user
        workspace = self.context.get('workspace')
        parent_id = validated_data.pop('parent', None)
        
        parent = None
        if parent_id:
            try:
                parent = Folder.objects.get(id=parent_id, workspace=workspace)
            except Folder.DoesNotExist:
                raise serializers.ValidationError({'parent': 'Invalid parent folder'})
        
        return Folder.objects.create(
            name=validated_data['name'],
            parent=parent,
            workspace=workspace,
            created_by=user
        )