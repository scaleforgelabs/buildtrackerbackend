import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0008_task_story_points'),
        ('workspaces', '0009_workspace_slug'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Sprint',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('goal', models.TextField(blank=True, null=True)),
                ('sprint_number', models.PositiveIntegerField()),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('status', models.CharField(
                    choices=[('planning', 'Planning'), ('active', 'Active'), ('completed', 'Completed')],
                    db_index=True,
                    default='planning',
                    max_length=20,
                )),
                ('duration_weeks', models.FloatField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('workspace', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sprints',
                    to='workspaces.workspace',
                )),
                ('created_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='created_sprints',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['sprint_number'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='sprint',
            unique_together={('workspace', 'sprint_number')},
        ),
    ]
