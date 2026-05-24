from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='ContentPost',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('platform', models.CharField(choices=[('twitter', 'Twitter/X'), ('instagram_post', 'Instagram Post'), ('instagram_slides', 'Instagram Slides'), ('linkedin', 'LinkedIn')], max_length=30)),
                ('content_pillar', models.CharField(blank=True, max_length=100)),
                ('tone', models.CharField(blank=True, max_length=60)),
                ('hook', models.TextField(blank=True)),
                ('full_copy', models.TextField(blank=True)),
                ('visual_direction', models.TextField(blank=True)),
                ('hashtags', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('to_do', 'To Do'), ('in_progress', 'In Progress'), ('scheduled', 'Scheduled'), ('posted', 'Posted'), ('skipped', 'Skipped')], db_index=True, default='to_do', max_length=20)),
                ('priority', models.CharField(choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High')], default='medium', max_length=10)),
                ('week', models.CharField(blank=True, max_length=20)),
                ('day', models.CharField(blank=True, max_length=10)),
                ('scheduled_date', models.DateField(blank=True, null=True)),
                ('posted_date', models.DateField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['platform', 'id'],
            },
        ),
        migrations.CreateModel(
            name='SalesLead',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('priority', models.CharField(choices=[('A', 'Tier A — Hot'), ('B', 'Tier B — Warm'), ('C', 'Tier C — Cold')], db_index=True, default='B', max_length=2)),
                ('company', models.CharField(max_length=200)),
                ('website', models.CharField(blank=True, max_length=200)),
                ('sector', models.CharField(blank=True, db_index=True, max_length=100)),
                ('stage', models.CharField(blank=True, db_index=True, max_length=50)),
                ('city', models.CharField(blank=True, max_length=100)),
                ('target_title', models.CharField(blank=True, max_length=300)),
                ('linkedin_search_url', models.TextField(blank=True)),
                ('pain_angle', models.TextField(blank=True)),
                ('dm_template', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('not_contacted', 'Not Contacted'), ('dm_sent', 'DM Sent'), ('replied', 'Replied'), ('call_booked', 'Call Booked'), ('demo_done', 'Demo Done'), ('converted', 'Converted'), ('not_interested', 'Not Interested'), ('no_response', 'No Response')], db_index=True, default='not_contacted', max_length=20)),
                ('date_contacted', models.DateField(blank=True, null=True)),
                ('follow_up_date', models.DateField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['priority', 'company'],
            },
        ),
    ]
