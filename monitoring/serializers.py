from rest_framework import serializers
from .models import SystemMetric, SystemAlert, UsageMetric

class SystemMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemMetric
        fields = ['id', 'metric_type', 'metric_name', 'value', 'unit', 'metadata', 'timestamp']

class SystemAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemAlert
        fields = ['id', 'alert_type', 'severity', 'status', 'title', 'description', 'metadata', 'created_at', 'resolved_at']

class ServiceHealthSerializer(serializers.Serializer):
    service_name = serializers.CharField()
    status = serializers.ChoiceField(choices=['healthy', 'degraded', 'down'])
    response_time = serializers.FloatField()
    last_check = serializers.DateTimeField()
    details = serializers.JSONField(required=False)

class PerformanceMetricsSerializer(serializers.Serializer):
    cpu_usage = serializers.FloatField()
    memory_usage = serializers.FloatField()
    disk_usage = serializers.FloatField()
    database_connections = serializers.IntegerField()
    cache_hit_rate = serializers.FloatField()
    avg_response_time = serializers.FloatField()

class SystemHealthSerializer(serializers.Serializer):
    system_status = serializers.ChoiceField(choices=['healthy', 'degraded', 'down'])
    services = ServiceHealthSerializer(many=True)
    performance_metrics = PerformanceMetricsSerializer()
    uptime = serializers.FloatField()

class AggregatedMetricsSerializer(serializers.Serializer):
    avg_response_time = serializers.FloatField()
    total_requests = serializers.IntegerField()
    error_rate = serializers.FloatField()
    peak_concurrent_users = serializers.IntegerField()

class UsageMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = UsageMetric
        fields = ['id', 'metric_name', 'value', 'unit', 'cost', 'date', 'metadata']

class DetailedUsageSerializer(serializers.Serializer):
    total_users = serializers.IntegerField()
    total_workspaces = serializers.IntegerField()
    total_tasks = serializers.IntegerField()
    storage_used = serializers.FloatField()
    api_calls = serializers.IntegerField()
    total_cost = serializers.DecimalField(max_digits=10, decimal_places=2)

class UsageTrendSerializer(serializers.Serializer):
    date = serializers.DateField()
    metric_name = serializers.CharField()
    value = serializers.FloatField()
    change_percentage = serializers.FloatField()

class CostBreakdownSerializer(serializers.Serializer):
    category = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    percentage = serializers.FloatField()

class OptimizationSuggestionSerializer(serializers.Serializer):
    category = serializers.CharField()
    suggestion = serializers.CharField()
    potential_savings = serializers.DecimalField(max_digits=10, decimal_places=2)
    priority = serializers.ChoiceField(choices=['low', 'medium', 'high'])