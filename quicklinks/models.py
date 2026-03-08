from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()

class QuickLinkCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quick_link_categories')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['name']
        unique_together = ['name', 'user']
    
    def __str__(self):
        return self.name

class QuickLink(models.Model):
    ENTITY_TYPE_CHOICES = [
        ('task', 'Task'),
        ('wiki', 'Wiki'),
        ('integration', 'Integration'),
        ('custom', 'Custom'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quick_links')
    title = models.CharField(max_length=255)
    url = models.URLField()
    icon = models.CharField(max_length=500, blank=True, null=True)
    category = models.CharField(max_length=100, blank=True, null=True)
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, null=True, blank=True)
    entity_type = models.CharField(max_length=20, choices=ENTITY_TYPE_CHOICES, default='custom')
    entity_id = models.CharField(max_length=255, blank=True, null=True)
    is_pinned = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['sort_order', '-created_at']
    
    def __str__(self):
        return self.title
        
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from cachalot.api import invalidate
        invalidate(self.__class__)
        
    def delete(self, *args, **kwargs):
        from cachalot.api import invalidate
        invalidate(self.__class__)
        super().delete(*args, **kwargs)

class SharedQuickLink(models.Model):
    VISIBILITY_CHOICES = [
        ('all_members', 'All Members'),
        ('admins_only', 'Admins Only'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='shared_quick_links')
    title = models.CharField(max_length=255)
    url = models.URLField()
    description = models.TextField(blank=True, null=True)
    icon = models.CharField(max_length=500, blank=True, null=True)
    category = models.CharField(max_length=100)
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='all_members')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_shared_links')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.workspace.name}"
        
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from cachalot.api import invalidate
        invalidate(self.__class__)
        
    def delete(self, *args, **kwargs):
        from cachalot.api import invalidate
        invalidate(self.__class__)
        super().delete(*args, **kwargs)

class RecentItem(models.Model):
    ITEM_TYPE_CHOICES = [
        ('task', 'Task'),
        ('wiki', 'Wiki'),
        ('workspace', 'Workspace'),
        ('integration', 'Integration'),
    ]
    
    ACTION_CHOICES = [
        ('viewed', 'Viewed'),
        ('edited', 'Edited'),
        ('created', 'Created'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recent_items')
    item_type = models.CharField(max_length=20, choices=ITEM_TYPE_CHOICES)
    item_id = models.CharField(max_length=255)
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, default='viewed')
    access_count = models.PositiveIntegerField(default=1)
    last_accessed = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-last_accessed']
        unique_together = ['user', 'item_type', 'item_id']
    
    def __str__(self):
        return f"{self.user.email} - {self.item_type} {self.item_id}"