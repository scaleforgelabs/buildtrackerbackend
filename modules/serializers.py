from rest_framework import serializers
from .models import ModuleAccess, ModulePreferences

class ModuleAccessSerializer(serializers.ModelSerializer):
    workspace_name = serializers.CharField(source='workspace.name', read_only=True)
    
    class Meta:
        model = ModuleAccess
        fields = ['id', 'module_name', 'workspace_name', 'session_duration', 
                 'actions_performed', 'accessed_at']

class ModuleAccessCreateSerializer(serializers.Serializer):
    module_name = serializers.ChoiceField(choices=ModuleAccess.MODULE_CHOICES)
    workspace_id = serializers.UUIDField(required=False, allow_null=True)
    session_duration = serializers.IntegerField(required=False, default=0)
    actions_performed = serializers.ListField(child=serializers.CharField(), required=False, default=list)

class ModulePreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModulePreferences
        fields = ['favorite_modules', 'module_order', 'quick_access_enabled', 'updated_at']
        read_only_fields = ['updated_at']

class UserActivitySerializer(serializers.Serializer):
    user_email = serializers.CharField()
    user_name = serializers.CharField()
    total_sessions = serializers.IntegerField()
    total_duration = serializers.IntegerField()
    last_access = serializers.DateTimeField()

class DailyUsageSerializer(serializers.Serializer):
    date = serializers.DateField()
    sessions = serializers.IntegerField()
    unique_users = serializers.IntegerField()
    total_duration = serializers.IntegerField()

class ModulePopularitySerializer(serializers.Serializer):
    module_name = serializers.CharField()
    total_sessions = serializers.IntegerField()
    unique_users = serializers.IntegerField()
    avg_duration = serializers.FloatField()
    popularity_score = serializers.FloatField()
