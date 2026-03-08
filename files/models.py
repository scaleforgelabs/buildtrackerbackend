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