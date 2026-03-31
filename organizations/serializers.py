from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Organization, OrganizationMembership, OrganizationUsage, OrganizationInvitation
from utils import sanitize_input, validate_organization_name, validate_email_format

User = get_user_model()

class UserBasicSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'avatar']

class OrganizationMembershipSerializer(serializers.ModelSerializer):
    user = UserBasicSerializer(read_only=True)
    
    class Meta:
        model = OrganizationMembership
        fields = ['id', 'user', 'role', 'joined_at', 'is_active']
        read_only_fields = ['id', 'user', 'role', 'joined_at']

class OrganizationUsageSerializer(serializers.ModelSerializer):
    usage_percentage = serializers.SerializerMethodField()
    limits_exceeded = serializers.SerializerMethodField()
    
    
    class Meta:
        model = OrganizationUsage
        fields = [
            'user_count', 'workspace_count', 'storage_used_mb', 'file_count',
            'last_calculated', 'usage_percentage', 'limits_exceeded'
        ]
    
    def get_usage_percentage(self, obj):
        return obj.get_usage_percentage()
    
    def get_limits_exceeded(self, obj):
        return obj.get_limits_exceeded()

class OrganizationSerializer(serializers.ModelSerializer):
    owner = UserBasicSerializer(read_only=True)
    member_count = serializers.ReadOnlyField()
    plan_limits = serializers.SerializerMethodField()
    usage = OrganizationUsageSerializer(read_only=True)
    plan_type = serializers.SerializerMethodField()
    
    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'owner', 'plan_type', 'billing_email',
            'created_at', 'updated_at', 'member_count', 'plan_limits', 'usage'
        ]
        read_only_fields = ['id', 'owner', 'plan_type', 'created_at', 'updated_at']
    
    def get_plan_type(self, obj):
        return obj.effective_plan_type

    def get_plan_limits(self, obj):
        return obj.get_plan_limits()
    
    def validate_name(self, value):
        cleaned_name = sanitize_input(value, max_length=100)
        is_valid, error_msg = validate_organization_name(cleaned_name)
        if not is_valid:
            raise serializers.ValidationError(error_msg)
        return cleaned_name
    
    def validate_billing_email(self, value):
        if value:
            cleaned_email = sanitize_input(value)
            is_valid, error_msg = validate_email_format(cleaned_email)
            if not is_valid:
                raise serializers.ValidationError(error_msg)
            return cleaned_email
        return value

class OrganizationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['name', 'billing_email']
    
    def validate_name(self, value):
        cleaned_name = sanitize_input(value, max_length=100)
        is_valid, error_msg = validate_organization_name(cleaned_name)
        if not is_valid:
            raise serializers.ValidationError(error_msg)
        return cleaned_name
    
    def create(self, validated_data):
        user = self.context['request'].user
        
        if Organization.objects.filter(owner=user).exists():
            raise serializers.ValidationError("User can only own one organization")
        
        organization = Organization.objects.create(
            owner=user,
            **validated_data
        )
        OrganizationMembership.objects.create(
            organization=organization,
            user=user,
            role='owner'
        )
        return organization

class OrganizationUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['name', 'billing_email']
    
    def validate_name(self, value):
        cleaned_name = sanitize_input(value, max_length=100)
        is_valid, error_msg = validate_organization_name(cleaned_name)
        if not is_valid:
            raise serializers.ValidationError(error_msg)
        return cleaned_name
    
    def validate_billing_email(self, value):
        if value:
            cleaned_email = sanitize_input(value)
            is_valid, error_msg = validate_email_format(cleaned_email)
            if not is_valid:
                raise serializers.ValidationError(error_msg)
            return cleaned_email
        return value

class OrganizationInvitationSerializer(serializers.ModelSerializer):
    invited_by = UserBasicSerializer(read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    
    class Meta:
        model = OrganizationInvitation
        fields = [
            'id', 'email', 'role', 'status', 'created_at', 'expires_at',
            'invited_by', 'organization_name'
        ]
        read_only_fields = ['id', 'status', 'created_at', 'expires_at', 'invited_by']

class PlanSerializer(serializers.Serializer):
    type = serializers.CharField()
    name = serializers.CharField()
    price_naira = serializers.IntegerField()
    price_usd = serializers.IntegerField()
    limits = serializers.DictField()
    features = serializers.ListField(child=serializers.CharField())

class UsageCheckSerializer(serializers.Serializer):
    can_add_user = serializers.BooleanField()
    can_create_workspace = serializers.BooleanField()
    can_upload_file = serializers.BooleanField()
    storage_available_mb = serializers.IntegerField()
    limits_exceeded = serializers.ListField(child=serializers.CharField())

class UsageDetailSerializer(serializers.Serializer):
    current_usage = serializers.DictField()
    limits = serializers.DictField()
    plan_type = serializers.CharField()
    usage_percentage = serializers.DictField()