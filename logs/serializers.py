from rest_framework import serializers
from .models import WorkspaceLog, AuditTrailLog, UserActivityLog, SystemEventLog

class WorkspaceLogSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name = serializers.SerializerMethodField()
    user_avatar = serializers.SerializerMethodField()
    
    class Meta:
        model = WorkspaceLog
        fields = ['id', 'log_type', 'severity', 'action', 'entity_type', 'entity_id', 
                 'description', 'metadata', 'user_email', 'user_name', 'user_avatar', 'ip_address', 'created_at']
    
    def get_user_name(self, obj):
        if obj.user:
            return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.email
        return "System"

    def get_user_avatar(self, obj):
        if obj.user and getattr(obj.user, 'avatar', None):
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.user.avatar.url)
            return obj.user.avatar.url
        return None

class AuditTrailLogSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = AuditTrailLog
        fields = ['id', 'action', 'entity_type', 'entity_id', 'old_values', 'new_values',
                 'user_email', 'ip_address', 'session_id', 'created_at']

class UserActivityLogSerializer(serializers.ModelSerializer):
    workspace_name = serializers.CharField(source='workspace.name', read_only=True)
    
    class Meta:
        model = UserActivityLog
        fields = ['id', 'activity_type', 'module', 'endpoint', 'duration_ms', 
                 'workspace_name', 'ip_address', 'session_id', 'metadata', 'created_at']

class SystemEventLogSerializer(serializers.ModelSerializer):
    workspace_name = serializers.CharField(source='workspace.name', read_only=True)
    
    class Meta:
        model = SystemEventLog
        fields = ['id', 'event_type', 'severity', 'message', 'source', 'error_code',
                 'workspace_name', 'resolved', 'resolved_at', 'created_at']

class ActivityTimelineItemSerializer(serializers.Serializer):
    timestamp = serializers.DateTimeField()
    action = serializers.CharField()
    user = serializers.CharField()
    description = serializers.CharField()
    entity_type = serializers.CharField()
    severity = serializers.CharField()

class DailyActivitySummarySerializer(serializers.Serializer):
    date = serializers.DateField()
    total_actions = serializers.IntegerField()
    unique_users = serializers.IntegerField()
    error_count = serializers.IntegerField()
    peak_hour = serializers.IntegerField()

class PeakActivitySerializer(serializers.Serializer):
    hour = serializers.IntegerField()
    activity_count = serializers.IntegerField()
    percentage = serializers.FloatField()

class LogSummarySerializer(serializers.Serializer):
    total_actions = serializers.IntegerField()
    unique_users = serializers.IntegerField()
    error_rate = serializers.FloatField()
    most_active_user = serializers.JSONField()

class SecurityEventSerializer(serializers.Serializer):
    event_type = serializers.CharField()
    severity = serializers.CharField()
    count = serializers.IntegerField()
    last_occurrence = serializers.DateTimeField()

class UserActivitySummarySerializer(serializers.Serializer):
    total_sessions = serializers.IntegerField()
    total_actions = serializers.IntegerField()
    modules_accessed = serializers.ListField(child=serializers.CharField())
    peak_activity_time = serializers.CharField()

class ProductivityMetricsSerializer(serializers.Serializer):
    tasks_completed = serializers.IntegerField()
    avg_session_duration = serializers.FloatField()
    most_used_feature = serializers.CharField()
    efficiency_score = serializers.FloatField()

class PersonalActivityStatsSerializer(serializers.Serializer):
    total_logins = serializers.IntegerField()
    total_actions = serializers.IntegerField()
    favorite_workspace = serializers.CharField()
    most_active_day = serializers.CharField()

class SystemHealthMetricsSerializer(serializers.Serializer):
    error_rate = serializers.FloatField()
    critical_events = serializers.IntegerField()
    avg_response_time = serializers.FloatField()
    uptime_percentage = serializers.FloatField()

class LogExportSerializer(serializers.Serializer):
    log_types = serializers.ListField(child=serializers.CharField())
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    format = serializers.ChoiceField(choices=['csv', 'json', 'excel'])
    include_metadata = serializers.BooleanField(default=False)