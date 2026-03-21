from rest_framework import serializers
from rest_framework import serializers
from .models import Task, TaskComment, TaskAttachment, TaskCommentAttachment, PersonalTask
from django.contrib.auth import get_user_model
from .tasks import send_task_assignment_email

User = get_user_model()

class TaskAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = TaskAttachment
        fields = ['id', 'file_url', 'file_name', 'file_size', 'uploaded_by', 'uploaded_at']
    
    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return obj.file_url

class TaskCommentAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = TaskCommentAttachment
        fields = ['id', 'file_url', 'file_name', 'file_size', 'uploaded_by', 'uploaded_at']
    
    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return obj.file_url

class TaskCommentSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    user_detail = serializers.SerializerMethodField()
    attachments = TaskCommentAttachmentSerializer(many=True, read_only=True)
    parent_comment_id = serializers.CharField(source='parent_comment.id', read_only=True)
    
    class Meta:
        model = TaskComment
        fields = ['id', 'comment_text', 'user', 'user_detail', 'user_name', 'parent_comment_id', 'attachments', 'created_at', 'updated_at']
        read_only_fields = ['user', 'created_at', 'updated_at']
    
    def get_user_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.email

    def get_user_detail(self, obj):
        request = self.context.get('request')
        profile_picture_url = None
        if hasattr(obj.user, 'avatar') and obj.user.avatar:
            profile_picture_url = obj.user.avatar.url
            if request:
                profile_picture_url = request.build_absolute_uri(profile_picture_url)
        return {
            'first_name': getattr(obj.user, 'first_name', ''),
            'last_name': getattr(obj.user, 'last_name', ''),
            'email': getattr(obj.user, 'email', ''),
            'profile_picture': profile_picture_url
        }

class TaskCommentCreateSerializer(serializers.ModelSerializer):
    attachments = serializers.ListField(
        required=False, 
        allow_empty=True,
        write_only=True
    )
    
    class Meta:
        model = TaskComment
        fields = ['comment_text', 'parent_comment_id', 'attachments']
    
    def create(self, validated_data):
        # Remove attachments from validated_data to avoid caching file objects
        validated_data.pop('attachments', [])
        task = self.context['task']
        user = self.context['request'].user
        request = self.context['request']
        
        # Handle parent_comment_id
        parent_comment_id = validated_data.pop('parent_comment_id', None)
        if parent_comment_id:
            try:
                parent_comment = TaskComment.objects.get(id=parent_comment_id, task=task)
                validated_data['parent_comment'] = parent_comment
            except TaskComment.DoesNotExist:
                pass
        
        comment = TaskComment.objects.create(
            task=task,
            user=user,
            **validated_data
        )
        
        # Handle file uploads from request.FILES
        if hasattr(request, 'FILES') and request.FILES:
            from utils import validate_file_security
            attachment_files = request.FILES.getlist('attachments')
            for attachment_file in attachment_files:
                is_valid, error = validate_file_security(attachment_file)
                if not is_valid:
                    raise serializers.ValidationError({'attachments': error})
                    
                TaskCommentAttachment.objects.create(
                    comment=comment,
                    file=attachment_file,
                    file_name=attachment_file.name,
                    uploaded_by=user
                )
        
        # Create notification for task owner/assignee
        from notifications.models import Notification
        user_name = f"{user.first_name} {user.last_name}".strip() or user.email
        if task.assigned_to and task.assigned_to != user:
            Notification.objects.create(
                user=task.assigned_to,
                workspace=task.workspace,
                action=f"{user_name} commented on: {task.task_name}",
                description=comment.comment_text[:100],
                note_type='task_comment',
                severity='info'
            )
        
        return comment

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'avatar']

class TaskSerializer(serializers.ModelSerializer):
    assigned_user = UserSerializer(source='assigned_to', read_only=True)
    created_by_user = UserSerializer(source='created_by', read_only=True)
    comments = TaskCommentSerializer(many=True, read_only=True)
    attachments = TaskAttachmentSerializer(many=True, read_only=True)
    
    class Meta:
        model = Task
        fields = [
            'id', 'task_name', 'task_description', 'assigned_to', 'assigned_user',
            'created_by', 'created_by_user', 'status', 'priority', 'start_date',
            'end_date', 'duration', 'milestone', 'sprint', 'percent_complete',
            'has_blocker', 'blocker_reason', 'ticket_number', 'created_at',
            'updated_at', 'comments', 'attachments'
        ]
        read_only_fields = ['ticket_number', 'created_by', 'created_at', 'updated_at', 'duration']
    
    def update(self, instance, validated_data):
        # Calculate duration if both dates are provided
        start_date = validated_data.get('start_date', instance.start_date)
        end_date = validated_data.get('end_date', instance.end_date)
        if start_date and end_date:
            sd = start_date.date() if hasattr(start_date, 'date') else start_date
            ed = end_date.date() if hasattr(end_date, 'date') else end_date
            duration_days = (ed - sd).days
            validated_data['duration'] = f"{duration_days} days"
        
        return super().update(instance, validated_data)

class TaskCreateSerializer(serializers.ModelSerializer):
    attachments = serializers.ListField(
        required=False, 
        allow_empty=True,
        write_only=True
    )
    assigned_to = serializers.UUIDField(required=True, error_messages={
        'required': 'Task must be assigned to a user',
        'invalid': 'Task must be assigned to a user',
        'null': 'Task must be assigned to a user'
    })
    
    class Meta:
        model = Task
        fields = [
            'task_name', 'task_description', 'assigned_to', 'priority', 'status',
            'start_date', 'end_date', 'milestone', 'sprint',
            'percent_complete', 'attachments'
        ]
    
    def validate_assigned_to(self, value):
        """Validate that assigned_to user exists and is a workspace member"""
        workspace = self.context['workspace']
        
        try:
            user = User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User does not exist")
        
        # Check if user is a member of the workspace
        from workspaces.models import WorkspaceMember
        if not WorkspaceMember.objects.filter(workspace=workspace, user=user).exists():
            raise serializers.ValidationError("User is not a member of this workspace")
        
        return user
    
    def create(self, validated_data):
        # Remove attachments from validated_data to avoid caching file objects
        validated_data.pop('attachments', [])
        workspace = self.context['workspace']
        user = self.context['request'].user
        request = self.context['request']
        
        # Calculate duration if both dates are provided
        start_date = validated_data.get('start_date')
        end_date = validated_data.get('end_date')
        if start_date and end_date:
            sd = start_date.date() if hasattr(start_date, 'date') else start_date
            ed = end_date.date() if hasattr(end_date, 'date') else end_date
            duration_days = (ed - sd).days
            validated_data['duration'] = f"{duration_days} days"
        
        # assigned_to is already a User object from validate_assigned_to
        task = Task.objects.create(
            workspace=workspace,
            created_by=user,
            **validated_data
        )
        
        # Handle file uploads from request.FILES
        if hasattr(request, 'FILES') and request.FILES:
            from utils import validate_file_security
            attachment_files = request.FILES.getlist('attachments')
            for attachment_file in attachment_files:
                # Security Validation
                is_valid, error = validate_file_security(attachment_file)
                if not is_valid:
                    raise serializers.ValidationError({'attachments': error})
                    
                TaskAttachment.objects.create(
                    task=task,
                    file=attachment_file,
                    file_name=attachment_file.name,
                    uploaded_by=user
                )
        
        # Create notification for assigned user
        from notifications.models import Notification
        assigner_name = f"{user.first_name} {user.last_name}".strip() or user.email
        assignee_name = f"{task.assigned_to.first_name} {task.assigned_to.last_name}".strip() or task.assigned_to.email
        
        if task.assigned_to:
            log_msg = f"Triggering assignment email for task {task.id} to {task.assigned_to.email}\n"
            print(log_msg, flush=True)
            with open('task_email_debug.log', 'a') as f:
                f.write(log_msg)
            Notification.objects.create(
                user=task.assigned_to,
                workspace=workspace,
                action=f"{assigner_name} assigned you to: {task.task_name}",
                description=f"You have been assigned to \"{task.task_name}\" by {assigner_name}",
                note_type='task_assigned',
                severity='info'
            )
            
            # Send email notification
            send_task_assignment_email.delay(task.id)
        
        return task

class PersonalTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonalTask
        fields = ['id', 'title', 'deadline', 'completed', 'created_at']
        read_only_fields = ['id', 'created_at']