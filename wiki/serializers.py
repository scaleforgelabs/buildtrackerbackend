from rest_framework import serializers
from .models import WikiDocument, WikiDocumentAttachment
from django.contrib.auth import get_user_model

User = get_user_model()

class WikiDocumentAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = WikiDocumentAttachment
        fields = ['id', 'file_url', 'file_name', 'file_size', 'uploaded_by', 'uploaded_at']
    
    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return obj.file_url

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'avatar']

class WikiDocumentSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    attachments = WikiDocumentAttachmentSerializer(many=True, read_only=True)
    
    class Meta:
        model = WikiDocument
        fields = ['id', 'document_title', 'document_description', 'category', 'visibility', 'image', 'author', 'attachments', 'created_at', 'updated_at']
        read_only_fields = ['author', 'created_at', 'updated_at']

class WikiDocumentCreateSerializer(serializers.ModelSerializer):
    attachments = serializers.ListField(
        required=False, 
        allow_empty=True,
        write_only=True
    )
    
    class Meta:
        model = WikiDocument
        fields = ['document_title', 'document_description', 'category', 'visibility', 'image', 'attachments']
    
    def create(self, validated_data):
        attachments_data = validated_data.pop('attachments', [])
        workspace = self.context['workspace']
        user = self.context['request'].user
        request = self.context['request']
        
        document = WikiDocument.objects.create(
            workspace=workspace,
            author=user,
            **validated_data
        )
        
        
        if hasattr(request, 'FILES') and request.FILES:
            from utils import validate_file_security
            attachment_files = request.FILES.getlist('attachments')
            for attachment_file in attachment_files:
                is_valid, error = validate_file_security(attachment_file)
                if not is_valid:
                    raise serializers.ValidationError({'attachments': error})
                    
                WikiDocumentAttachment.objects.create(
                    document=document,
                    file=attachment_file,
                    file_name=attachment_file.name,
                    uploaded_by=user
                )
        
        
        for attachment in attachments_data:
            if isinstance(attachment, str) and attachment.startswith(('http://', 'https://')):
                WikiDocumentAttachment.objects.create(
                    document=document,
                    file_url=attachment,
                    file_name=attachment.split('/')[-1],
                    uploaded_by=user
                )
        
        return document