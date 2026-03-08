from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()

class Integration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='integrations')
    name = models.CharField(max_length=255)
    icon = models.CharField(max_length=500, blank=True, null=True)
    url = models.URLField(blank=True, null=True)
    category = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_integrations')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_visible = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} - {self.workspace.name}"
        
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from cachalot.api import invalidate
        invalidate(self.__class__)

    def delete(self, *args, **kwargs):
        from cachalot.api import invalidate
        invalidate(self.__class__)
        super().delete(*args, **kwargs)
