from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auth_func', '0008_customuser_platform_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='scheduled_for_deletion_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
