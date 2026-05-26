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
    
    def _get_descendant_folder_ids(self):
        """
        Return the set of PKs for this folder and all descendants.
        Uses 1 query (all folders in the workspace) instead of O(depth) recursive queries.
        """
        all_pairs = list(
            Folder.objects.filter(workspace_id=self.workspace_id)
            .values_list('id', 'parent_id')
        )
        children_map: dict = {}
        for fid, parent_id in all_pairs:
            if parent_id is not None:
                children_map.setdefault(parent_id, []).append(fid)

        ids = set()
        queue = [self.pk]
        while queue:
            current = queue.pop()
            ids.add(current)
            queue.extend(children_map.get(current, []))
        return ids

    def get_all_subfolders(self):
        """Return all nested subfolders using 1 query instead of O(depth) recursive queries."""
        descendant_ids = self._get_descendant_folder_ids()
        descendant_ids.discard(self.pk)  # exclude self
        return list(Folder.objects.filter(id__in=descendant_ids))

    def get_total_size(self):
        """Calculate total size of all files in this folder and subfolders (2 queries, not O(depth))."""
        from django.db.models import Sum
        all_folder_ids = self._get_descendant_folder_ids()
        result = File.objects.filter(folder_id__in=all_folder_ids).aggregate(total=Sum('file_size'))
        return result['total'] or 0

    def get_item_count(self):
        """Count only immediate items (files + subfolders) in this folder."""
        return self.files.count() + self.subfolders.count()

    def get_contributors(self):
        """Get unique contributors (uploaders + folder creators) across all descendants (2 queries)."""
        all_folder_ids = self._get_descendant_folder_ids()
        uploader_ids = set(
            File.objects.filter(folder_id__in=all_folder_ids)
            .values_list('uploaded_by', flat=True)
        )
        creator_ids = set(
            Folder.objects.filter(id__in=all_folder_ids)
            .values_list('created_by', flat=True)
        )
        all_ids = uploader_ids | creator_ids
        return User.objects.filter(id__in=all_ids)

    def get_contributors_ids(self):
        """Return uploader IDs for this folder and all descendants (2 queries)."""
        all_folder_ids = self._get_descendant_folder_ids()
        return set(
            File.objects.filter(folder_id__in=all_folder_ids)
            .values_list('uploaded_by', flat=True)
        )

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