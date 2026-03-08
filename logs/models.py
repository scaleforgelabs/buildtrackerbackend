from django.db import models
from django.contrib.auth import get_user_model
import uuid
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex

User = get_user_model()

class WorkspaceLog(models.Model):
    LOG_TYPES = [
        ('task_create', 'Task Created'),
        ('task_update', 'Task Updated'),
        ('task_status_change', 'Task Status Changed'),
        ('task_delete', 'Task Deleted'),
        ('comment_create', 'Comment Created'),
        ('comment_update', 'Comment Updated'),
        ('comment_delete', 'Comment Deleted'),
        ('team_update', 'Team Updated'),
        ('wiki_create', 'Wiki Created'),
        ('wiki_update', 'Wiki Updated'),
        ('wiki_delete', 'Wiki Deleted'),
        ('integration_create', 'Integration Created'),
        ('integration_update', 'Integration Updated'),
        ('integration_delete', 'Integration Deleted'),
        ('workspace_update', 'Workspace Updated'),
        ('member_add', 'Member Added'),
        ('member_remove', 'Member Removed'),
        ('file_upload', 'File Uploaded'),
        ('backup_create', 'Backup Created'),
        ('settings_update', 'Settings Updated'),
    ]
    
    SEVERITY_LEVELS = [
        ('info', 'Info'),
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='logs')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    log_type = models.CharField(max_length=50, choices=LOG_TYPES)
    severity = models.CharField(max_length=20, choices=SEVERITY_LEVELS, default='info')
    action = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=50, blank=True)
    entity_id = models.UUIDField(null=True, blank=True)
    description = models.TextField()
    metadata = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    search_vector = SearchVectorField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        app_label = 'logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['workspace', 'log_type', 'created_at']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['severity', 'created_at']),
            models.Index(fields=['entity_type', 'entity_id']),
            models.Index(fields=['created_at']),
            GinIndex(fields=['search_vector']),
        ]
    
    def __str__(self):
        return f"{self.log_type} - {self.workspace.name} - {self.created_at}"
        
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from django.contrib.postgres.search import SearchVector
        WorkspaceLog.objects.filter(pk=self.pk).update(
            search_vector=SearchVector('action', 'description')
        )

class AuditTrailLog(models.Model):
    ACTION_TYPES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('view', 'View'),
        ('export', 'Export'),
        ('login', 'Login'),
        ('logout', 'Logout'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='audit_logs')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_TYPES)
    entity_type = models.CharField(max_length=50)
    entity_id = models.UUIDField(null=True, blank=True)
    old_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    session_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        app_label = 'logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['workspace', 'action', 'created_at']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['entity_type', 'entity_id']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.action} {self.entity_type} - {self.workspace.name}"

class UserActivityLog(models.Model):
    ACTIVITY_TYPES = [
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('page_view', 'Page View'),
        ('api_call', 'API Call'),
        ('file_download', 'File Download'),
        ('search', 'Search'),
        ('export', 'Export'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activity_logs')
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='user_activities', null=True, blank=True)
    activity_type = models.CharField(max_length=50, choices=ACTIVITY_TYPES)
    module = models.CharField(max_length=50, blank=True)
    endpoint = models.CharField(max_length=200, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    session_id = models.CharField(max_length=100, blank=True)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        app_label = 'logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'workspace', 'created_at']),
            models.Index(fields=['activity_type', 'created_at']),
            models.Index(fields=['session_id', 'created_at']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.activity_type} - {self.created_at}"

class SystemEventLog(models.Model):
    EVENT_TYPES = [
        ('error', 'Error'),
        ('warning', 'Warning'),
        ('info', 'Info'),
        ('security', 'Security'),
        ('performance', 'Performance'),
    ]
    
    SEVERITY_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='system_events', null=True, blank=True)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    severity = models.CharField(max_length=20, choices=SEVERITY_LEVELS)
    message = models.TextField()
    source = models.CharField(max_length=100)
    error_code = models.CharField(max_length=50, blank=True)
    stack_trace = models.TextField(blank=True)
    metadata = models.JSONField(default=dict)
    resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        app_label = 'logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['workspace', 'event_type', 'created_at']),
            models.Index(fields=['severity', 'resolved', 'created_at']),
            models.Index(fields=['event_type', 'severity']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.event_type} - {self.severity} - {self.created_at}"