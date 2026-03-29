from rest_framework import serializers
from .models import Notification
from django.contrib.auth import get_user_model

User = get_user_model()

class NotificationSerializer(serializers.ModelSerializer):
    user_avatar = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()
    triggered_by_avatar = serializers.SerializerMethodField()
    triggered_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ['id', 'user', 'workspace', 'action', 'description', 'note_type', 'severity', 'is_read', 'created_at', 'read_at', 'user_avatar', 'user_name', 'triggered_by', 'triggered_by_avatar', 'triggered_by_name']
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

    def get_triggered_by_avatar(self, obj):
        if hasattr(obj, 'triggered_by') and obj.triggered_by and hasattr(obj.triggered_by, 'avatar') and obj.triggered_by.avatar:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.triggered_by.avatar.url)
            return obj.triggered_by.avatar.url
            
        name = self.get_triggered_by_name(obj)
        if name:
            name_parts = name.split(" ")
            if len(name_parts) >= 1:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                users = User.objects.filter(first_name__iexact=name_parts[0])
                if len(name_parts) > 1:
                    users = users.filter(last_name__iexact=" ".join(name_parts[1:]))
                user = users.first()
                if user and hasattr(user, 'avatar') and user.avatar:
                    request = self.context.get('request')
                    if request:
                        return request.build_absolute_uri(user.avatar.url)
                    return user.avatar.url
        return None

    def get_triggered_by_name(self, obj):
        if hasattr(obj, 'triggered_by') and obj.triggered_by:
            first = getattr(obj.triggered_by, 'first_name', '')
            last = getattr(obj.triggered_by, 'last_name', '')
            full_name = f"{first} {last}".strip()
            if full_name:
                return full_name
            email = getattr(obj.triggered_by, 'email', '')
            if email:
                return email.split('@')[0]
                
        import re
        if obj.description:
            match = re.search(r'by (.+)$', obj.description)
            if match:
                return match.group(1).replace('"', '').replace("'", "").strip()
        
        if obj.action:
            action_str = str(obj.action)
            if " assigned you to" in action_str:
                return action_str.split(" assigned ")[0]
            if " commented on" in action_str:
                return action_str.split(" commented ")[0]
            if " updated " in action_str:
                return action_str.split(" updated ")[0]
            if " set a blocker" in action_str:
                return action_str.split(" set ")[0]
            if " cleared blocker" in action_str:
                return action_str.split(" cleared ")[0]
                
        return None

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
