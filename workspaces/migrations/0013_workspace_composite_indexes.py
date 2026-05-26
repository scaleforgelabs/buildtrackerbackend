from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('workspaces', '0012_add_checkin_module'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='workspace',
            index=models.Index(fields=['organization', 'status'], name='workspace_org_status_idx'),
        ),
        migrations.AddIndex(
            model_name='workspace',
            index=models.Index(fields=['owner', 'status'], name='workspace_owner_status_idx'),
        ),
        migrations.AddIndex(
            model_name='workspaceinvitation',
            index=models.Index(fields=['workspace', 'status'], name='wsinvite_workspace_status_idx'),
        ),
    ]
