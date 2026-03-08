from django.db import models
from auth_func.models import CustomUser
import uuid


class DashboardWidget(models.Model):
    WIDGET_TYPES = [
        ('task_summary', 'Task Summary'),
        ('recent_tasks', 'Recent Tasks'),
        ('team_performance', 'Team Performance'),
        ('milestone_progress', 'Milestone Progress'),
        ('sprint_burndown', 'Sprint Burndown'),
        ('priority_distribution', 'Priority Distribution'),
        ('status_chart', 'Status Chart'),
        ('overdue_tasks', 'Overdue Tasks'),
        ('completion_trend', 'Completion Trend'),
        ('velocity_chart', 'Velocity Chart'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='dashboard_widgets')
    widget_type = models.CharField(max_length=50, choices=WIDGET_TYPES)
    title = models.CharField(max_length=200)
    position_x = models.IntegerField(default=0)
    position_y = models.IntegerField(default=0)
    width = models.IntegerField(default=4)
    height = models.IntegerField(default=4)
    is_visible = models.BooleanField(default=True)
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['position_y', 'position_x']
        unique_together = ['user', 'widget_type']
    
    def __str__(self):
        return f"{self.user.email} - {self.title}"


class WidgetLayout(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='widget_layout')
    layout_config = models.JSONField(default=dict)
    columns = models.IntegerField(default=12)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Layout for {self.user.email}"
