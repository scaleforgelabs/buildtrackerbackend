from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0009_sprint'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='task',
            index=models.Index(fields=['workspace', 'status'], name='task_workspace_status_idx'),
        ),
        migrations.AddIndex(
            model_name='task',
            index=models.Index(fields=['workspace', 'assigned_to'], name='task_workspace_assigned_idx'),
        ),
        migrations.AddIndex(
            model_name='task',
            index=models.Index(fields=['workspace', 'created_at'], name='task_workspace_created_idx'),
        ),
    ]
