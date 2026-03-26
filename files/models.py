from django.db import models
from django.contrib.auth import get_user_model
import uuid
import os

User = get_user_model()

class Folder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='folders')
    name = models.CharField(max_length=255)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subfolders')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_folders')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        unique_together = ['workspace', 'parent', 'name']
    
    def __str__(self):
        return self.name
    
    def get_path(self):
        """Get full path of folder"""
        if self.parent:
            return f"{self.parent.get_path()}/{self.name}"
        return self.name
    
    def get_all_subfolders(self):
        """Get all nested subfolders"""
        subfolders = list(self.subfolders.all())
        for subfolder in self.subfolders.all():
            subfolders.extend(subfolder.get_all_subfolders())
        return subfolders

    def get_total_size(self):
        """Recursively calculate total size of all files in this folder and subfolders"""
        total = sum(file.file_size for file in self.files.all())
        for subfolder in self.subfolders.all():
            total += subfolder.get_total_size()
        return total

    def get_item_count(self):
        """Count only immediate items (files + subfolders) in this folder"""
        return self.files.count() + self.subfolders.count()

    def get_contributors(self):
        """Get unique set of users (recursive) who have created subfolders or uploaded files"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # All contributors recursively (uploaders)
        user_ids = self.get_contributors_ids()
        
        # Add this folder's creator
        user_ids.add(self.created_by_id)
        
        # Add subfolders' creators recursively
        for subfolder in self.get_all_subfolders():
            user_ids.add(subfolder.created_by_id)
            
        return User.objects.filter(id__in=user_ids)

    def get_contributors_ids(self):
        """Helper to get uploader IDs recursively"""
        ids = set(self.files.values_list('uploaded_by', flat=True))
        for subfolder in self.subfolders.all():
            ids.update(subfolder.get_contributors_ids())
        return ids

class File(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='files', null=True, blank=True)
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, related_name='files', null=True, blank=True)
    file = models.FileField(upload_to='uploads/')
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=50)
    file_size = models.PositiveIntegerField()
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_files')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-uploaded_at']
        unique_together = ['workspace', 'folder', 'file_name']
    
    def __str__(self):
        return self.file_name
    
    def get_path(self):
        """Get full path of file"""
        if self.folder:
            return f"{self.folder.get_path()}/{self.file_name}"
        return self.file_name
    
    def save(self, *args, **kwargs):
        if self.file:
            # Only set initial metadata if this is a new file or metadata is missing
            if not self.file_name:
                self.file_name = os.path.basename(self.file.name)
            
            # Update size and type if they are missing
            if not self.file_size:
                self.file_size = self.file.size
            if not self.file_type:
                self.file_type = os.path.splitext(self.file.name)[1].lower().replace('.', '')
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        if self.file:
            self.file.delete(save=False)
        super().delete(*args, **kwargs)