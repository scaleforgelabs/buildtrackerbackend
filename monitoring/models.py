from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()

class SystemMetric(models.Model):
    METRIC_TYPES = [
        ('performance', 'Performance'),
        ('usage', 'Usage'),
        ('error', 'Error'),
        ('security', 'Security'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    metric_type = models.CharField(max_length=20, choices=METRIC_TYPES)
    metric_name = models.CharField(max_length=100)
    value = models.FloatField()
    unit = models.CharField(max_length=20)
    metadata = models.JSONField(default=dict)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        app_label = 'monitoring'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['metric_type', 'timestamp']),
            models.Index(fields=['metric_name', 'timestamp']),
            models.Index(fields=['timestamp']),
        ]
    
    def __str__(self):
        return f"{self.metric_name}: {self.value} {self.unit}"

class SystemAlert(models.Model):
    SEVERITY_LEVELS = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('critical', 'Critical'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('resolved', 'Resolved'),
        ('acknowledged', 'Acknowledged'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alert_type = models.CharField(max_length=50)
    severity = models.CharField(max_length=20, choices=SEVERITY_LEVELS)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField()
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        app_label = 'monitoring'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['severity', 'status', 'created_at']),
            models.Index(fields=['alert_type', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} ({self.severity})"

class UsageMetric(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('organizations.Organization', on_delete=models.CASCADE, related_name='usage_metrics')
    metric_name = models.CharField(max_length=100)
    value = models.FloatField()
    unit = models.CharField(max_length=20)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    date = models.DateField()
    metadata = models.JSONField(default=dict)
    
    class Meta:
        app_label = 'monitoring'
        ordering = ['-date']
        indexes = [
            models.Index(fields=['organization', 'metric_name', 'date']),
            models.Index(fields=['organization', 'date']),
            models.Index(fields=['date']),
        ]
        unique_together = ['organization', 'metric_name', 'date']
    
    def __str__(self):
        return f"{self.organization.name} - {self.metric_name}: {self.value}"