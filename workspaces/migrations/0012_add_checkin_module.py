from django.db import migrations


def add_checkin_module(apps, schema_editor):
    WorkspaceSettings = apps.get_model('workspaces', 'WorkspaceSettings')
    for settings in WorkspaceSettings.objects.all():
        modules = settings.enabled_modules or {}
        if 'checkin' not in modules:
            modules['checkin'] = True
            settings.enabled_modules = modules
            settings.save(update_fields=['enabled_modules'])


class Migration(migrations.Migration):

    dependencies = [
        ('workspaces', '0011_add_gantt_module'),
    ]

    operations = [
        migrations.RunPython(add_checkin_module, migrations.RunPython.noop),
    ]
