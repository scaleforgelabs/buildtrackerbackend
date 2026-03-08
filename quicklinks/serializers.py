from rest_framework import serializers
from django.db import models
from .models import QuickLink, QuickLinkCategory, SharedQuickLink, RecentItem
from django.contrib.auth import get_user_model
from utils import sanitize_input

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name']

class QuickLinkCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = QuickLinkCategory
        fields = ['id', 'name', 'created_at']
        read_only_fields = ['created_at']

class QuickLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuickLink
        fields = ['id', 'title', 'url', 'icon', 'category', 'workspace', 'entity_type', 'entity_id', 'is_pinned', 'sort_order', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

class QuickLinkCreateSerializer(serializers.ModelSerializer):
    category = serializers.CharField(max_length=100, allow_blank=True, required=False)
    
    class Meta:
        model = QuickLink
        fields = ['title', 'url', 'icon', 'category', 'workspace_id', 'entity_type', 'entity_id']
    
    def validate_title(self, value):
        return sanitize_input(value, max_length=255)
    
    def create(self, validated_data):
        user = self.context['request'].user
        workspace_id = validated_data.pop('workspace_id', None)
        
        # Get the highest sort_order for this user
        max_order = QuickLink.objects.filter(user=user).aggregate(
            max_order=models.Max('sort_order')
        )['max_order'] or 0
        
        quick_link = QuickLink.objects.create(
            user=user,
            workspace_id=workspace_id,
            sort_order=max_order + 1,
            **validated_data
        )
        
        return quick_link

class SharedQuickLinkSerializer(serializers.ModelSerializer):
    created_by_user = UserSerializer(source='created_by', read_only=True)
    
    class Meta:
        model = SharedQuickLink
        fields = ['id', 'title', 'url', 'description', 'icon', 'category', 'visibility', 'created_by_user', 'created_at', 'updated_at']
        read_only_fields = ['created_by', 'created_at', 'updated_at']

class SharedQuickLinkCreateSerializer(serializers.ModelSerializer):
    category = serializers.CharField(max_length=100, allow_blank=True, required=False)
    
    class Meta:
        model = SharedQuickLink
        fields = ['title', 'url', 'description', 'icon', 'category', 'visibility']
    
    def validate_title(self, value):
        return sanitize_input(value, max_length=255)
    
    def create(self, validated_data):
        workspace = self.context['workspace']
        user = self.context['request'].user
        
        shared_link = SharedQuickLink.objects.create(
            workspace=workspace,
            created_by=user,
            **validated_data
        )
        
        return shared_link

class RecentItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecentItem
        fields = ['id', 'item_type', 'item_id', 'workspace', 'action', 'access_count', 'last_accessed', 'created_at']
        read_only_fields = ['access_count', 'last_accessed', 'created_at']

class RecentItemCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecentItem
        fields = ['item_type', 'item_id', 'workspace_id', 'action']
    
    def create(self, validated_data):
        user = self.context['request'].user
        workspace_id = validated_data.pop('workspace_id', None)
        
        # Try to get existing recent item
        recent_item, created = RecentItem.objects.get_or_create(
            user=user,
            item_type=validated_data['item_type'],
            item_id=validated_data['item_id'],
            defaults={
                'workspace_id': workspace_id,
                'action': validated_data['action']
            }
        )
        
        if not created:
            # Update existing item
            recent_item.access_count += 1
            recent_item.action = validated_data['action']
            recent_item.save()
        
        return recent_item

class FrequentItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecentItem
        fields = ['id', 'item_type', 'item_id', 'workspace', 'access_count', 'last_accessed']