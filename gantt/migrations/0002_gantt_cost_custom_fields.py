from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gantt', '0001_initial'),
    ]

    operations = [
        # GanttProject: custom field schema
        migrations.AddField(
            model_name='ganttproject',
            name='custom_field_schema',
            field=models.JSONField(default=list),
        ),
        # GanttTask: cost + custom field values
        migrations.AddField(
            model_name='gantttask',
            name='estimated_cost',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name='gantttask',
            name='actual_cost',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name='gantttask',
            name='custom_fields',
            field=models.JSONField(default=dict),
        ),
    ]
