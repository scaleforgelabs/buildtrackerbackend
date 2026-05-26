from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0007_alter_task_end_date_alter_task_start_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='story_points',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
