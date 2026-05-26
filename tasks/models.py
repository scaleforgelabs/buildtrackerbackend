from django.db import models
from django.contrib.auth import get_user_model
import uuid
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex

User = get_user_model()


def _update_search_vector_async(task_pk):
    """Dispatch search vector update to Celery worker."""
    from tasks.tasks import update_task_search_vector
    update_task_search_vector.delay(task_pk)

class Task(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='tasks')
    task_name = models.CharField(max_length=255)
    task_description = models.TextField(blank=True, null=True)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tasks')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_tasks')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium', db_index=True)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    duration = models.CharField(max_length=50, blank=True, null=True)
    milestone = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    sprint = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    story_points = models.PositiveIntegerField(null=True, blank=True)
    percent_complete = models.PositiveIntegerField(default=0)
    has_blocker = models.BooleanField(default=False)
    blocker_reason = models.TextField(blank=True, null=True)
    ticket_number = models.PositiveIntegerField()
    search_vector = SearchVectorField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['workspace', 'ticket_number']
        indexes = [
            GinIndex(fields=['search_vector']),
            models.Index(fields=['workspace', 'status'],      name='task_workspace_status_idx'),
            models.Index(fields=['workspace', 'assigned_to'], name='task_workspace_assigned_idx'),
            models.Index(fields=['workspace', 'created_at'],  name='task_workspace_created_idx'),
        ]
    
    def __str__(self):
        return f"#{self.ticket_number} - {self.task_name}"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._old_status = self.status
        self._old_has_blocker = self.has_blocker
        self._old_assigned_to = self.assigned_to_id if self.pk else None
    
    def save(self, *args, **kwargs):
        if not self.ticket_number:
            from django.db import transaction, IntegrityError
            # Use select_for_update to prevent race conditions on concurrent task creation
            # within the same workspace. Retry on IntegrityError as a safety net.
            for attempt in range(3):
                try:
                    with transaction.atomic():
                        last_task = (
                            Task.objects.filter(workspace=self.workspace)
                            .select_for_update()
                            .order_by('-ticket_number')
                            .first()
                        )
                        self.ticket_number = (last_task.ticket_number + 1) if last_task else 1
                        super().save(*args, **kwargs)
                    break
                except IntegrityError:
                    if attempt == 2:
                        raise  # Give up after 3 attempts
                    self.ticket_number = None  # Reset for retry
                    continue
        else:
            super().save(*args, **kwargs)
        
        # Offload SearchVector update to Celery to avoid a blocking query on every save.
        # Uses transaction.on_commit to ensure the task only fires after the save is committed.
        from django.db import transaction
        task_pk = str(self.pk)
        transaction.on_commit(lambda: _update_search_vector_async(task_pk))
        
        self._old_status = self.status
        self._old_has_blocker = self.has_blocker
        self._old_assigned_to = self.assigned_to_id

class TaskComment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    comment_text = models.TextField()
    parent_comment = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Comment on {self.task.task_name} by {self.user.email}"

class TaskCommentAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    comment = models.ForeignKey(TaskComment, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='comment_attachments/', null=True, blank=True)
    file_url = models.URLField(null=True, blank=True)
    file_name = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(null=True, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.file_name} - Comment Attachment"
    
    def save(self, *args, **kwargs):
        if self.file and not self.file_name:
            self.file_name = self.file.name
        if self.file and not self.file_size:
            self.file_size = self.file.size
        super().save(*args, **kwargs)

class TaskAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='task_attachments/', null=True, blank=True)
    file_url = models.URLField(null=True, blank=True)
    file_name = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(null=True, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.file_name} - {self.task.task_name}"
    
    def save(self, *args, **kwargs):
        if self.file and not self.file_name:
            self.file_name = self.file.name
        if self.file and not self.file_size:
            self.file_size = self.file.size
        super().save(*args, **kwargs)

class Sprint(models.Model):
    STATUS_CHOICES = [
        ('planning', 'Planning'),
        ('active', 'Active'),
        ('completed', 'Completed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='sprints')
    name = models.CharField(max_length=255)
    goal = models.TextField(blank=True, null=True)
    sprint_number = models.PositiveIntegerField()
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planning', db_index=True)
    duration_weeks = models.FloatField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_sprints')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sprint_number']
        unique_together = ['workspace', 'sprint_number']

    def __str__(self):
        return f"Sprint {self.sprint_number} - {self.name}"


class PersonalTask(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='personal_tasks')
    title = models.CharField(max_length=255)
    deadline = models.DateTimeField(null=True, blank=True)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} (Personal Task)"