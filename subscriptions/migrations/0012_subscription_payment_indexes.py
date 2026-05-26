from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0011_planpricing'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='subscription',
            index=models.Index(fields=['status', 'next_billing_date'], name='sub_status_billing_idx'),
        ),
        migrations.AddIndex(
            model_name='paymenthistory',
            index=models.Index(fields=['organization', 'status'], name='payment_org_status_idx'),
        ),
        migrations.AddIndex(
            model_name='paymenthistory',
            index=models.Index(fields=['status', 'transaction_date'], name='payment_status_date_idx'),
        ),
    ]
