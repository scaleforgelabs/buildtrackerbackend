from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auth_func', '0007_customuser_last_active_workspace'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='platform_role',
            field=models.CharField(
                choices=[
                    ('user', 'User'),
                    ('admin', 'Admin'),
                    ('super_admin', 'Super Admin'),
                ],
                db_index=True,
                default='user',
                max_length=20,
            ),
        ),
    ]
