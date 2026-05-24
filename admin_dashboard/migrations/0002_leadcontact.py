from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('admin_dashboard', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='LeadContact',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200)),
                ('title', models.CharField(blank=True, max_length=200)),
                ('linkedin_url', models.TextField(blank=True)),
                ('phone', models.CharField(blank=True, max_length=50)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('twitter_handle', models.CharField(blank=True, max_length=100)),
                ('outreach_status', models.CharField(choices=[('not_contacted', 'Not Contacted'), ('dm_sent', 'DM Sent'), ('replied', 'Replied'), ('call_booked', 'Call Booked'), ('not_interested', 'Not Interested'), ('no_response', 'No Response')], default='not_contacted', max_length=20)),
                ('date_contacted', models.DateField(blank=True, null=True)),
                ('follow_up_date', models.DateField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('lead', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contacts', to='admin_dashboard.saleslead')),
            ],
            options={
                'ordering': ['name'],
            },
        ),
    ]
