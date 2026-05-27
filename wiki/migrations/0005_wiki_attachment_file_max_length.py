from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wiki', '0004_alter_wikidocument_created_at'),
    ]

    operations = [
        migrations.AlterField(
            model_name='wikidocumentattachment',
            name='file',
            field=models.FileField(blank=True, max_length=500, null=True, upload_to='wiki_attachments/'),
        ),
    ]
