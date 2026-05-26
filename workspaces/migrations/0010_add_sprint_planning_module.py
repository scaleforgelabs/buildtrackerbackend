from django.db import migrations


def add_sprint_planning_to_existing(apps, schema_editor):
    WorkspaceSettings = apps.get_model('workspaces', 'WorkspaceSettings')
    for settings in WorkspaceSettings.objects.all():
        if 'sprint_planning' not in settings.enabled_modules:
            settings.enabled_modules['sprint_planning'] = True
            settings.save(update_fields=['enabled_modules'])


class Migration(migrations.Migration):

    dependencies = [
        ('workspaces', '0009_workspace_slug'),
    ]

    operations = [
        migrations.RunPython(add_sprint_planning_to_existing, migrations.RunPython.noop),
    ]
