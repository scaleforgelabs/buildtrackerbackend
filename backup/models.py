from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()

class BackupJob(models.Model):
    BACKUP_TYPES = [
        ('full', 'Full Backup'),
        ('incremental', 'Incremental Backup'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='backup_jobs')
    backup_type = models.CharField(max_length=20, choices=BACKUP_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    include_files = models.BooleanField(default=True)
    encryption_enabled = models.BooleanField(default=False)
    file_url = models.URLField(blank=True)
    file_size = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    class Meta:
        app_label = 'backup'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['workspace', 'backup_type', 'created_at']),
            models.Index(fields=['status', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.backup_type} backup for {self.workspace.name}"

class ExportJob(models.Model):
    EXPORT_TYPES = [
        ('complete', 'Complete Export'),
        ('tasks_only', 'Tasks Only'),
        ('wiki_only', 'Wiki Only'),
        ('users_only', 'Users Only'),
    ]
    
    FORMAT_CHOICES = [
        ('json', 'JSON'),
        ('csv', 'CSV'),
        ('excel', 'Excel'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='export_jobs')
    export_type = models.CharField(max_length=20, choices=EXPORT_TYPES)
    format = models.CharField(max_length=10, choices=FORMAT_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    date_range = models.JSONField(default=dict, blank=True)
    file_url = models.URLField(blank=True)
    file_size = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    class Meta:
        app_label = 'backup'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['workspace', 'export_type', 'created_at']),
            models.Index(fields=['status', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.export_type} export for {self.workspace.name}"