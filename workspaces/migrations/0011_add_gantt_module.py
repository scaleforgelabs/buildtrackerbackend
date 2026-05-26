from django.db import migrations


def add_gantt_to_existing(apps, schema_editor):
    WorkspaceSettings = apps.get_model('workspaces', 'WorkspaceSettings')
    for settings in WorkspaceSettings.objects.all():
        if 'gantt' not in settings.enabled_modules:
            settings.enabled_modules['gantt'] = True
            settings.save(update_fields=['enabled_modules'])


class Migration(migrations.Migration):

    dependencies = [
        ('workspaces', '0010_add_sprint_planning_module'),
    ]

    operations = [
        migrations.RunPython(add_gantt_to_existing, migrations.RunPython.noop),
    ]
