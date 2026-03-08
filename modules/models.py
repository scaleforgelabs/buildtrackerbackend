from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()

class ModuleAccess(models.Model):
    MODULE_CHOICES = [
        ('dashboard', 'Dashboard'),
        ('tasks', 'Tasks'),
        ('team', 'Team'),
        ('wiki', 'Wiki'),
        ('integrations', 'Integrations'),
        ('logs', 'Logs'),
        ('reports', 'Reports'),
        ('modules', 'Modules'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='module_accesses')
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='module_accesses', null=True, blank=True)
    module_name = models.CharField(max_length=50, choices=MODULE_CHOICES)
    session_duration = models.PositiveIntegerField(default=0)
    actions_performed = models.JSONField(default=list)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    accessed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-accessed_at']
        indexes = [
            models.Index(fields=['user', 'module_name', 'accessed_at']),
            models.Index(fields=['workspace', 'module_name', 'accessed_at']),
            models.Index(fields=['module_name', 'accessed_at']),
            models.Index(fields=['accessed_at']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.module_name} - {self.accessed_at}"

class ModulePreferences(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='module_preferences')
    favorite_modules = models.JSONField(default=list)
    module_order = models.JSONField(default=list)
    quick_access_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"Preferences for {self.user.email}"
