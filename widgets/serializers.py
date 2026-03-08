from rest_framework import serializers
from .models import DashboardWidget, WidgetLayout


class DashboardWidgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardWidget
        fields = ['id', 'widget_type', 'title', 'position_x', 'position_y', 
                  'width', 'height', 'is_visible', 'config', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class WidgetLayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = WidgetLayout
        fields = ['id', 'layout_config', 'columns', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class AvailableWidgetSerializer(serializers.Serializer):
    widget_type = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    default_width = serializers.IntegerField()
    default_height = serializers.IntegerField()
    category = serializers.CharField()


class UserDashboardSerializer(serializers.Serializer):
    widgets = DashboardWidgetSerializer(many=True)
    layout = WidgetLayoutSerializer()
    available_widgets = AvailableWidgetSerializer(many=True)


class UpdateDashboardSerializer(serializers.Serializer):
    widgets = DashboardWidgetSerializer(many=True)
    layout = WidgetLayoutSerializer()


class WidgetDataSerializer(serializers.Serializer):
    widget_data = serializers.JSONField()
    last_updated = serializers.DateTimeField()
    refresh_interval = serializers.IntegerField()
