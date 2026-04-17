from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


class DailyCheckIn(models.Model):
    SENTIMENT_CHOICES = [
        ('GREAT', 'Great'),
        ('GOOD', 'Good'),
        ('NEUTRAL', 'Neutral'),
        ('BAD', 'Bad'),
        ('TERRIBLE', 'Terrible'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='checkins'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='checkins'
    )
    sentiment = models.CharField(max_length=10, choices=SENTIMENT_CHOICES, default='GOOD')
    yesterday_progress = models.TextField(blank=True, default='')
    tomorrow_plan = models.TextField(blank=True, default='')
    has_blockers = models.BooleanField(default=False)
    yesterday_tasks = models.ManyToManyField(
        'tasks.Task',
        blank=True,
        related_name='checkin_yesterday'
    )
    tomorrow_tasks = models.ManyToManyField(
        'tasks.Task',
        blank=True,
        related_name='checkin_tomorrow'
    )
    # date is used to enforce one check-in per user per workspace per day
    date = models.DateField(auto_now_add=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        # One check-in per user per workspace per day
        unique_together = ['workspace', 'user', 'date']

    def __str__(self):
        return f"{self.user.email} check-in for {self.workspace.name} on {self.date}"


class CheckInBlocker(models.Model):
    PRIORITY_CHOICES = [
        ('HIGH', 'High'),
        ('MED', 'Medium'),
        ('LOW', 'Low'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    checkin = models.ForeignKey(
        DailyCheckIn,
        on_delete=models.CASCADE,
        related_name='blockers'
    )
    description = models.TextField()
    # null notify_member means "notify everybody"
    notify_member = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='blocker_mentions'
    )
    priority = models.CharField(max_length=4, choices=PRIORITY_CHOICES, default='HIGH')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Blocker on {self.checkin} [{self.priority}]"
