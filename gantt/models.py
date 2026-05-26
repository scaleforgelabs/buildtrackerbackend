import uuid
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class GanttProject(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        'workspaces.Workspace', on_delete=models.CASCADE, related_name='gantt_projects'
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    # Schema: [{"id": "uuid", "name": "Risk", "type": "select|text|number|date|checkbox", "options": [...]}]
    custom_field_schema = models.JSONField(default=list)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='created_gantt_projects'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.workspace.name})"


class GanttTask(models.Model):
    TASK_TYPE_CHOICES = [
        ('task', 'Task'),
        ('milestone', 'Milestone'),
        ('project', 'Project'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        GanttProject, on_delete=models.CASCADE, related_name='tasks'
    )
    name = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    progress = models.PositiveIntegerField(default=0)  # 0–100
    task_type = models.CharField(max_length=20, choices=TASK_TYPE_CHOICES, default='task', db_index=True)
    # Comma-separated list of GanttTask UUIDs this task depends on (finish-to-start)
    dependencies = models.TextField(blank=True, null=True)
    assignee = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='gantt_tasks'
    )
    notes = models.TextField(blank=True, null=True)
    parent_task = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children'
    )
    estimated_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    actual_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    # Values keyed by custom field id from project.custom_field_schema
    custom_fields = models.JSONField(default=dict)
    display_order = models.PositiveIntegerField(default=0, db_index=True)
    hide_children = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'created_at']

    def __str__(self):
        return f"{self.name} [{self.project.name}]"
