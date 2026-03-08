from rest_framework import serializers
from .models import Notification
from django.contrib.auth import get_user_model

User = get_user_model()

class NotificationSerializer(serializers.ModelSerializer):
    user_avatar = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ['id', 'user', 'workspace', 'action', 'description', 'note_type', 'severity', 'is_read', 'created_at', 'read_at', 'user_avatar', 'user_name']
        read_only_fields = ['id', 'user', 'created_at', 'read_at']
        
    def get_user_avatar(self, obj):
        if hasattr(obj, 'user') and hasattr(obj.user, 'avatar') and obj.user.avatar:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.user.avatar.url)
            return obj.user.avatar.url
        return None

    def get_user_name(self, obj):
        if hasattr(obj, 'user') and obj.user:
            first = getattr(obj.user, 'first_name', '')
            last = getattr(obj.user, 'last_name', '')
            full_name = f"{first} {last}".strip()
            if full_name:
                return full_name
            email = getattr(obj.user, 'email', '')
            if email:
                return email.split('@')[0]
        return "User"

class NotificationCreateSerializer(serializers.ModelSerializer):
    workspace_id = serializers.UUIDField(required=False, allow_null=True)
    
    class Meta:
        model = Notification
        fields = ['workspace_id', 'action', 'description', 'note_type', 'severity']
    
    def validate_workspace_id(self, value):
        if value:
            from workspaces.models import Workspace
            try:
                workspace = Workspace.objects.get(id=value)
                return workspace
            except Workspace.DoesNotExist:
                raise serializers.ValidationError("Workspace does not exist")
        return None
    
    def create(self, validated_data):
        user = self.context['request'].user
        workspace = validated_data.pop('workspace_id', None)
        
        notification = Notification.objects.create(
            user=user,
            workspace=workspace,
            **validated_data
        )
        return notification
