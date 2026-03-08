from rest_framework import serializers
from .models import WaitlistEntry
from utils import sanitize_input, validate_email_format

class WaitlistEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = WaitlistEntry
        fields = ['id', 'email', 'created_at']
        read_only_fields = ['id', 'created_at']

class WaitlistCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WaitlistEntry
        fields = ['email']
    
    def validate_email(self, value):
        cleaned_email = sanitize_input(value)
        is_valid, error_msg = validate_email_format(cleaned_email)
        if not is_valid:
            raise serializers.ValidationError(error_msg)
        
        # Check if email already exists
        if WaitlistEntry.objects.filter(email=cleaned_email).exists():
            raise serializers.ValidationError("Email already exists in waitlist")
        
        return cleaned_email