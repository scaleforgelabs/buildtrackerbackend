from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()

class Report(models.Model):
    REPORT_TYPES = [
        ('task_summary', 'Task Summary'),
        ('user_performance', 'User Performance'),
        ('workspace_overview', 'Workspace Overview'),
        ('time_tracking', 'Time Tracking'),
        ('milestone_progress', 'Milestone Progress'),
        ('sprint_report', 'Sprint Report'),
        ('personal_performance', 'Personal Performance'),
        ('task_history', 'Task History'),
        ('time_summary', 'Time Summary'),
        ('achievement_report', 'Achievement Report'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    FORMAT_CHOICES = [
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
        ('csv', 'CSV'),
        ('json', 'JSON'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='reports', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports', null=True, blank=True)
    report_type = models.CharField(max_length=50, choices=REPORT_TYPES)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    format = models.CharField(max_length=10, choices=FORMAT_CHOICES, default='json')
    parameters = models.JSONField(default=dict)
    data = models.JSONField(default=dict)
    file_url = models.URLField(blank=True)
    job_id = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_reports')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        app_label = 'reports'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['workspace', 'report_type', 'created_at']),
            models.Index(fields=['user', 'report_type', 'created_at']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['job_id']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.report_type}"

class ReportTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    report_type = models.CharField(max_length=50, choices=Report.REPORT_TYPES)
    category = models.CharField(max_length=100)
    description = models.TextField()
    template_config = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        app_label = 'reports'
        ordering = ['category', 'name']
        indexes = [
            models.Index(fields=['report_type', 'is_active']),
            models.Index(fields=['category', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.category})"

class ScheduledReport(models.Model):
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='scheduled_reports')
    report_type = models.CharField(max_length=50, choices=Report.REPORT_TYPES)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    recipients = models.JSONField(default=list)
    parameters = models.JSONField(default=dict)
    next_run = models.DateTimeField()
    last_run = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        app_label = 'reports'
        ordering = ['next_run']
        indexes = [
            models.Index(fields=['workspace', 'is_active', 'next_run']),
            models.Index(fields=['frequency', 'is_active', 'next_run']),
        ]
    
    def __str__(self):
        return f"{self.report_type} - {self.frequency}"

class SharedReport(models.Model):
    ACCESS_LEVELS = [
        ('view', 'View Only'),
        ('download', 'Download'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='shared_links')
    shared_by = models.ForeignKey(User, on_delete=models.CASCADE)
    recipients = models.JSONField(default=list)
    access_level = models.CharField(max_length=20, choices=ACCESS_LEVELS)
    message = models.TextField(blank=True)
    share_token = models.CharField(max_length=100, unique=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        app_label = 'reports'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['share_token']),
            models.Index(fields=['report', 'expires_at']),
        ]
    
    def __str__(self):
        return f"Shared: {self.report.title}"