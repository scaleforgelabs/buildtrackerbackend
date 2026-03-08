from rest_framework import serializers
from .models import BackupJob, ExportJob

class BackupJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackupJob
        fields = ['id', 'backup_type', 'status', 'include_files', 'encryption_enabled', 
                 'file_url', 'file_size', 'created_at', 'completed_at', 'error_message']
        read_only_fields = ['id', 'status', 'file_url', 'file_size', 'created_at', 'completed_at', 'error_message']

class BackupCreateSerializer(serializers.Serializer):
    backup_type = serializers.ChoiceField(choices=BackupJob.BACKUP_TYPES)
    include_files = serializers.BooleanField(default=True)
    encryption_enabled = serializers.BooleanField(default=False)

class ExportJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExportJob
        fields = ['id', 'export_type', 'format', 'status', 'date_range', 
                 'file_url', 'file_size', 'created_at', 'completed_at', 'error_message']
        read_only_fields = ['id', 'status', 'file_url', 'file_size', 'created_at', 'completed_at', 'error_message']

class ExportCreateSerializer(serializers.Serializer):
    export_type = serializers.ChoiceField(choices=ExportJob.EXPORT_TYPES)
    format = serializers.ChoiceField(choices=ExportJob.FORMAT_CHOICES)
    date_range = serializers.JSONField(required=False)
    
    def validate_date_range(self, value):
        if value:
            if 'from' in value and 'to' in value:
                try:
                    from datetime import datetime
                    datetime.strptime(value['from'], '%Y-%m-%d')
                    datetime.strptime(value['to'], '%Y-%m-%d')
                except ValueError:
                    raise serializers.ValidationError("Invalid date format. Use YYYY-MM-DD")
        return value