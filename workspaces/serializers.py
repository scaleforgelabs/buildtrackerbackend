from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Workspace, WorkspaceMember, WorkspaceInvitation, WorkspaceSettings
from utils import sanitize_input, validate_email_format

User = get_user_model()

class UserBasicSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'avatar']

class WorkspaceMemberSerializer(serializers.ModelSerializer):
    user = UserBasicSerializer(read_only=True)
    
    class Meta:
        model = WorkspaceMember
        fields = ['id', 'user', 'name', 'phone', 'job_role', 'role', 'user_status', 'joined_at', 'email']
        read_only_fields = ['id', 'user', 'joined_at', 'email']

class WorkspaceSerializer(serializers.ModelSerializer):
    owner = UserBasicSerializer(read_only=True)
    member_count = serializers.SerializerMethodField()
    user_role = serializers.SerializerMethodField()
    
    class Meta:
        model = Workspace
        fields = ['id', 'name', 'description', 'type', 'owner', 'created_at', 'updated_at', 'no_of_tickets', 'member_count', 'user_role']
        read_only_fields = ['id', 'owner', 'created_at', 'updated_at', 'no_of_tickets']
    
    def get_member_count(self, obj):
        if hasattr(obj, 'member_count'):
            return obj.member_count
        return obj.members.count()
    
    def get_user_role(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            # Avoid N+1 by using prefetched members if available
            for member in obj.members.all():
                if member.user_id == request.user.id:
                    return member.role
            return None
        return None
    
    def validate_name(self, value):
        return sanitize_input(value, max_length=255)
    
    def validate_description(self, value):
        if value:
            return sanitize_input(value, max_length=1000)
        return value

class WorkspaceCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workspace
        fields = ['name', 'description', 'type']
    
    def validate_name(self, value):
        return sanitize_input(value, max_length=255)
    
    def validate_description(self, value):
        if value:
            return sanitize_input(value, max_length=1000)
        return value
    
    def create(self, validated_data):
        user = self.context['request'].user
        
        workspace = Workspace.objects.create(
            owner=user, 
            **validated_data
        )
        WorkspaceMember.objects.create(
            workspace=workspace, 
            user=user, 
            role='Owner', 
            email=user.email
        )
        
        return workspace

class WorkspaceInvitationSerializer(serializers.ModelSerializer):
    invited_by = UserBasicSerializer(read_only=True)
    workspace_name = serializers.CharField(source='workspace.name', read_only=True)
    
    class Meta:
        model = WorkspaceInvitation
        fields = ['id', 'email', 'phone', 'job_role', 'role', 'status', 'user_status', 'created_at', 'expires_at', 'invited_by', 'workspace_name']
        read_only_fields = ['id', 'status', 'created_at', 'expires_at', 'invited_by']
    
    def validate_email(self, value):
        cleaned_email = sanitize_input(value)
        is_valid, error_msg = validate_email_format(cleaned_email)
        if not is_valid:
            raise serializers.ValidationError(error_msg)
        return cleaned_email

class WorkspaceMemberCreateSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(write_only=True)
    
    class Meta:
        model = WorkspaceMember
        fields = ['user_id', 'role', 'name', 'phone', 'job_role']
    
    def validate_name(self, value):
        if value:
            return sanitize_input(value, max_length=100)
        return value
    
    def validate_phone(self, value):
        if value:
            return sanitize_input(value, max_length=20)
        return value
    
    def validate_job_role(self, value):
        if value:
            return sanitize_input(value, max_length=100)
        return value
    
    def create(self, validated_data):
        user_id = validated_data.pop('user_id')
        workspace = self.context['workspace']
        
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found")
        
        if WorkspaceMember.objects.filter(workspace=workspace, user=user).exists():
            raise serializers.ValidationError("User is already a member of this workspace")
        
        # Check workspace owner plan limits
        from organizations.user_org_views import calculate_user_stats, get_plan_limits
        current_usage = calculate_user_stats(workspace.owner)
        limits = get_plan_limits(workspace.owner.plan_type)
        
        if current_usage['user_count'] >= limits['max_users']:
            raise serializers.ValidationError("User limit exceeded for workspace owner plan")
        
        return WorkspaceMember.objects.create(
            workspace=workspace,
            user=user,
            email=user.email,
            **validated_data
        )
class WorkspaceSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkspaceSettings
        fields = ['timezone', 'date_format', 'notifications_enabled', 'auto_assign_tasks', 'default_task_priority', 'enabled_modules', 'updated_at']
        read_only_fields = ['updated_at']

class WorkspacePermissionsSerializer(serializers.Serializer):
    can_edit_settings = serializers.BooleanField()
    can_manage_members = serializers.BooleanField()
    can_create_tasks = serializers.BooleanField()
    can_delete_workspace = serializers.BooleanField()
    can_create_backups = serializers.BooleanField()

class WorkspaceSettingsUpdateSerializer(serializers.Serializer):
    timezone = serializers.ChoiceField(choices=WorkspaceSettings.TIMEZONE_CHOICES, required=False)
    date_format = serializers.ChoiceField(choices=WorkspaceSettings.DATE_FORMAT_CHOICES, required=False)
    notifications_enabled = serializers.BooleanField(required=False)
    auto_assign_tasks = serializers.BooleanField(required=False)
    default_task_priority = serializers.ChoiceField(choices=WorkspaceSettings.PRIORITY_CHOICES, required=False)
    enabled_modules = serializers.JSONField(required=False)