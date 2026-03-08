from rest_framework import serializers
from .models import Integration
from django.contrib.auth import get_user_model

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name']

class IntegrationSerializer(serializers.ModelSerializer):
    creator = UserSerializer(source='created_by', read_only=True)
    
    class Meta:
        model = Integration
        fields = ['id', 'name', 'icon', 'url', 'category', 'description', 'creator', 'created_at', 'updated_at', 'is_visible']
        read_only_fields = ['created_by', 'created_at', 'updated_at']

class IntegrationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Integration
        fields = ['name', 'icon', 'url', 'category', 'description', 'is_visible']
    
    def create(self, validated_data):
        workspace = self.context['workspace']
        user = self.context['request'].user
        
        integration = Integration.objects.create(
            workspace=workspace,
            created_by=user,
            **validated_data
        )
        
        return integration