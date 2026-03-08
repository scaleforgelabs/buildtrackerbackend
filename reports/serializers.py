from rest_framework import serializers
from .models import Report, ReportTemplate, ScheduledReport, SharedReport
from utils import sanitize_input

class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = ['id', 'report_type', 'title', 'description', 'status', 'format', 
                 'parameters', 'file_url', 'created_at', 'updated_at', 'completed_at', 'expires_at']
        read_only_fields = ['id', 'status', 'file_url', 'created_at', 'updated_at', 'completed_at']
    
    def validate_title(self, value):
        return sanitize_input(value)
    
    def validate_description(self, value):
        return sanitize_input(value) if value else value

class ReportGenerateSerializer(serializers.Serializer):
    report_type = serializers.ChoiceField(choices=Report.REPORT_TYPES)
    parameters = serializers.CharField(default='{}', allow_blank=True)
    schedule = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    
    def validate_parameters(self, value):
        if not value or value == '':
            return {}
        if isinstance(value, str):
            import json
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return {}
        if isinstance(value, dict):
            for key, val in value.items():
                if isinstance(val, str):
                    value[key] = sanitize_input(val)
        return value
    
    def validate_schedule(self, value):
        if not value or value == '':
            return None
        if isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return value

class PersonalReportGenerateSerializer(serializers.Serializer):
    PERSONAL_REPORT_TYPES = [
        ('personal_performance', 'Personal Performance'),
        ('task_history', 'Task History'),
        ('time_summary', 'Time Summary'),
        ('achievement_report', 'Achievement Report'),
    ]
    
    report_type = serializers.ChoiceField(choices=PERSONAL_REPORT_TYPES, default='personal_performance')
    parameters = serializers.JSONField(default=dict, required=False)
    
    def validate_parameters(self, value):
        if isinstance(value, dict):
            for key, val in value.items():
                if isinstance(val, str):
                    value[key] = sanitize_input(val)
        return value

class ReportTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportTemplate
        fields = ['id', 'name', 'report_type', 'category', 'description', 'template_config']

class ScheduledReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScheduledReport
        fields = ['id', 'report_type', 'frequency', 'recipients', 'parameters', 
                 'next_run', 'last_run', 'is_active', 'created_at']
        read_only_fields = ['id', 'last_run', 'created_at']
    
    def validate_recipients(self, value):
        if not isinstance(value, list) or not value:
            raise serializers.ValidationError("Recipients must be a non-empty list")
        return value

class SharedReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = SharedReport
        fields = ['id', 'recipients', 'access_level', 'message', 'share_token', 
                 'expires_at', 'created_at']
        read_only_fields = ['id', 'share_token', 'created_at']
    
    def validate_message(self, value):
        return sanitize_input(value) if value else value

class ReportShareSerializer(serializers.Serializer):
    recipients = serializers.ListField(child=serializers.EmailField())
    message = serializers.CharField(required=False, allow_blank=True)
    access_level = serializers.ChoiceField(choices=SharedReport.ACCESS_LEVELS)
    
    def validate_message(self, value):
        return sanitize_input(value) if value else value
    
    def validate_recipients(self, value):
        if not value:
            raise serializers.ValidationError("At least one recipient is required")
        return value

class ReportDataSerializer(serializers.Serializer):
    summary = serializers.JSONField()
    data = serializers.JSONField()
    charts = serializers.JSONField(required=False)
    metadata = serializers.JSONField(required=False)

class PerformanceSummarySerializer(serializers.Serializer):
    total_tasks = serializers.IntegerField()
    completed_tasks = serializers.IntegerField()
    completion_rate = serializers.FloatField()
    average_completion_time = serializers.FloatField()
    productivity_score = serializers.FloatField()