from django.db import models
from django.contrib.auth import get_user_model
import uuid
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

User = get_user_model()

class Organization(models.Model):
    PLAN_CHOICES = [
        ('free', 'Starter Organization'),
        ('pro', 'Pro Organization'),
        ('business', 'Business Organization'),
        ('enterprise', 'Enterprise Organization'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('cancelled', 'Cancelled'),
        ('suspended', 'Suspended'),
        ('trial', 'Trial'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_organizations')
    members = models.ManyToManyField(User, through='OrganizationMembership', related_name='organization_memberships')
    plan_type = models.CharField(max_length=20, choices=PLAN_CHOICES, default='free')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)
    billing_email = models.EmailField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name
    
    @property
    def member_count(self):
        return self.members.count()
    
    def get_plan_limits(self):
        limits = {
            'free': {'max_users': 5, 'max_workspaces': 2, 'max_storage_mb': 2048},
            'pro': {'max_users': 10, 'max_workspaces': 10, 'max_storage_mb': 10240},
            'business': {'max_users': 30, 'max_workspaces': 30, 'max_storage_mb': 102400},
            'enterprise': {'max_users': 999999, 'max_workspaces': 999999, 'max_storage_mb': 999999999},
        }
        return limits.get(self.plan_type, limits['free'])
    
    def can_add_user(self):
        return self.member_count < self.get_plan_limits()['max_users']
    
    def can_create_workspace(self):
        return self.workspaces.count() < self.get_plan_limits()['max_workspaces']
    
    def can_upload_file(self, file_size_mb=0):
        current_usage = self.get_current_usage()
        return (current_usage['storage_used_mb'] + file_size_mb) <= self.get_plan_limits()['max_storage_mb']
    
    def get_current_usage(self):
        usage, created = OrganizationUsage.objects.get_or_create(
            organization=self,
            defaults={
                'user_count': self.member_count,
                'workspace_count': self.workspaces.count(),
                'storage_used_mb': 0,
                'file_count': 0
            }
        )
        return {
            'user_count': usage.user_count,
            'workspace_count': usage.workspace_count,
            'storage_used_mb': usage.storage_used_mb,
            'file_count': usage.file_count
        }

class OrganizationMembership(models.Model):
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('admin', 'Admin'),
        ('member', 'Member'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['organization', 'user']
        ordering = ['-joined_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.organization.name} ({self.role})"

class OrganizationUsage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name='usage')
    user_count = models.PositiveIntegerField(default=0)
    workspace_count = models.PositiveIntegerField(default=0)
    storage_used_mb = models.PositiveIntegerField(default=0)
    file_count = models.PositiveIntegerField(default=0)
    last_calculated = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Usage for {self.organization.name}"
    
    def get_usage_percentage(self):
        limits = self.organization.get_plan_limits()
        return {
            'users': (self.user_count / limits['max_users']) * 100 if limits['max_users'] > 0 else 0,
            'workspaces': (self.workspace_count / limits['max_workspaces']) * 100 if limits['max_workspaces'] > 0 else 0,
            'storage': (self.storage_used_mb / limits['max_storage_mb']) * 100 if limits['max_storage_mb'] > 0 else 0,
        }
    
    def get_limits_exceeded(self):
        limits = self.organization.get_plan_limits()
        exceeded = []
        
        if self.user_count >= limits['max_users']:
            exceeded.append('users')
        if self.workspace_count >= limits['max_workspaces']:
            exceeded.append('workspaces')
        if self.storage_used_mb >= limits['max_storage_mb']:
            exceeded.append('storage')
        
        return exceeded

class OrganizationInvitation(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField()
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invitations')
    role = models.CharField(max_length=20, choices=OrganizationMembership.ROLE_CHOICES, default='member')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    token = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField()
    
    class Meta:
        unique_together = ['organization', 'email']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Invitation to {self.email} for {self.organization.name}"
    
    def is_expired(self):
        return timezone.now() > self.expires_at
    
    def is_valid(self):
        return self.status == 'pending' and not self.is_expired()