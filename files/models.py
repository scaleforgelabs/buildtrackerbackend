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
        """Get unique set of users (excluding the creator) who have uploaded files in this folder or subfolders"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        uploader_ids = set(self.files.values_list('uploaded_by', flat=True))
        for subfolder in self.subfolders.all():
            uploader_ids.update(subfolder.get_contributors_ids())
        
        # Exclude the folder creator from the contributors list
        return User.objects.filter(id__in=uploader_ids).exclude(id=self.created_by_id)

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
            self.file_name = self.file.name
            self.file_size = self.file.size
            self.file_type = os.path.splitext(self.file.name)[1].lower().replace('.', '')
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        if self.file:
            self.file.delete(save=False)
        super().delete(*args, **kwargs)