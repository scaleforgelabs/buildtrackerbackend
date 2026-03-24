from django.db import models
from django.contrib.auth import get_user_model
import uuid
from django.utils import timezone

User = get_user_model()

class Workspace(models.Model):
    TYPE_CHOICES = [
        ('Construction', 'Construction'),
        ('Software', 'Software'),
        ('Event', 'Event'),
        ('Other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('archived', 'Archived'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.TextField()
    description = models.TextField(blank=True, null=True)
    type = models.TextField(choices=TYPE_CHOICES, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_workspaces')
    organization = models.ForeignKey('organizations.Organization', on_delete=models.CASCADE, related_name='workspaces', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    no_of_tickets = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name

class WorkspaceMember(models.Model):
    ROLE_CHOICES = [
        ('Owner', 'Owner'),
        ('Admin', 'Admin'),
        ('Member', 'Member'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('busy', 'Busy'),
        ('offline', 'Offline'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='workspace_memberships')
    name = models.TextField(blank=True, null=True)
    phone = models.TextField(blank=True, null=True)
    job_role = models.TextField(blank=True, null=True)
    role = models.TextField(choices=ROLE_CHOICES, db_index=True)
    user_status = models.TextField(choices=STATUS_CHOICES, default='active', db_index=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    email = models.TextField(blank=True, null=True)
    
    class Meta:
        unique_together = ['workspace', 'user']
        ordering = ['-joined_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.workspace.name} ({self.role})"

class WorkspaceInvitation(models.Model):
    ROLE_CHOICES = [
        ('Admin', 'Admin'),
        ('Member', 'Member'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
    ]
    
    USER_STATUS_CHOICES = [
        ('active', 'Active'),
        ('busy', 'Busy'),
        ('offline', 'Offline'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='invitations')
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_workspace_invitations')
    email = models.TextField()
    phone = models.TextField(blank=True, null=True)
    job_role = models.TextField(blank=True, null=True)
    role = models.TextField(choices=ROLE_CHOICES)
    status = models.TextField(choices=STATUS_CHOICES, default='pending', db_index=True)
    user_status = models.TextField(choices=USER_STATUS_CHOICES, default='active', db_index=True)
    token = models.TextField(unique=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Invitation to {self.email} for {self.workspace.name}"
    
    def is_expired(self):
        return timezone.now() > self.expires_at
    
    def is_valid(self):
        return self.status == 'pending' and not self.is_expired()

def default_modules():
    return {
        "planning": True,
        "my_tasks": True,
        "logs": True
    }

class WorkspaceSettings(models.Model):
    TIMEZONE_CHOICES = [
        ('UTC', 'UTC'),
        ('America/New_York', 'Eastern Time'),
        ('America/Chicago', 'Central Time'),
        ('America/Denver', 'Mountain Time'),
        ('America/Los_Angeles', 'Pacific Time'),
        ('Europe/London', 'London'),
        ('Europe/Paris', 'Paris'),
        ('Asia/Tokyo', 'Tokyo'),
    ]
    
    DATE_FORMAT_CHOICES = [
        ('MM/DD/YYYY', 'MM/DD/YYYY'),
        ('DD/MM/YYYY', 'DD/MM/YYYY'),
        ('YYYY-MM-DD', 'YYYY-MM-DD'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.OneToOneField(Workspace, on_delete=models.CASCADE, related_name='settings')
    timezone = models.CharField(max_length=50, choices=TIMEZONE_CHOICES, default='UTC')
    date_format = models.CharField(max_length=20, choices=DATE_FORMAT_CHOICES, default='MM/DD/YYYY')
    notifications_enabled = models.BooleanField(default=True)
    auto_assign_tasks = models.BooleanField(default=False)
    default_task_priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    enabled_modules = models.JSONField(default=default_modules)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"Settings for {self.workspace.name}"