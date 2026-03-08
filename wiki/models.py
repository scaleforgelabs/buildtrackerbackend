from django.db import models
from django.contrib.auth import get_user_model
import uuid
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex

User = get_user_model()

class WikiDocument(models.Model):
    VISIBILITY_CHOICES = [
        ('private', 'Private'),
        ('public', 'Public'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='wiki_documents')
    document_title = models.CharField(max_length=255)
    document_description = models.TextField(blank=True, null=True)
    category = models.CharField(max_length=100, blank=True, null=True)
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default='private')
    image = models.ImageField(upload_to='wiki_covers/', blank=True, null=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wiki_documents')
    search_vector = SearchVectorField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
        indexes = [
            GinIndex(fields=['search_vector']),
        ]
    
    def __str__(self):
        return self.document_title
        
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from django.contrib.postgres.search import SearchVector
        WikiDocument.objects.filter(pk=self.pk).update(
            search_vector=SearchVector('document_title', 'document_description', 'category')
        )
        
        from cachalot.api import invalidate
        invalidate(WikiDocument)

    def delete(self, *args, **kwargs):
        from cachalot.api import invalidate
        invalidate(WikiDocument)
        super().delete(*args, **kwargs)

class WikiDocumentAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(WikiDocument, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='wiki_attachments/', null=True, blank=True)
    file_url = models.URLField(null=True, blank=True)
    file_name = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(null=True, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.file_name} - {self.document.document_title}"
    
    def save(self, *args, **kwargs):
        if self.file and not self.file_name:
            self.file_name = self.file.name
        if self.file and not self.file_size:
            self.file_size = self.file.size
        super().save(*args, **kwargs)