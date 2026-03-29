from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()

class Notification(models.Model):
    SEVERITY_CHOICES = [
        ('info', 'Info'),
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    triggered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='triggered_notifications')
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    action = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    note_type = models.CharField(max_length=100, blank=True, null=True)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='info')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['workspace', 'is_read']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.action} - {self.user.email}"
