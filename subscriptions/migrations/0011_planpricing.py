"""
Migration: Create PlanPricing table and seed initial prices.

Seeded values match the BuildTracker Pricing Guide v1.0 (2025):
  Starter — ₦9,900/mo · ₦7,900/mo yearly · $6/mo · $5/mo yearly
  Premium — ₦24,900/mo · ₦19,900/mo yearly · $15/mo · $12/mo yearly
  Custom  — ₦95,000/mo · ₦75,000/mo yearly · $60/mo · $45/mo yearly  (floor prices)
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_plan_pricing(apps, schema_editor):
    """Insert the initial plan prices from the pricing guide."""
    PlanPricing = apps.get_model('subscriptions', 'PlanPricing')
    PlanPricing.objects.bulk_create([
        PlanPricing(
            plan_type='starter',
            price_ngn_monthly=9900,
            price_ngn_yearly=7900,
            price_usd_monthly=6,
            price_usd_yearly=5,
        ),
        PlanPricing(
            plan_type='premium',
            price_ngn_monthly=24900,
            price_ngn_yearly=19900,
            price_usd_monthly=15,
            price_usd_yearly=12,
        ),
        PlanPricing(
            plan_type='custom',
            price_ngn_monthly=95000,
            price_ngn_yearly=75000,
            price_usd_monthly=60,
            price_usd_yearly=45,
        ),
    ])


def remove_plan_pricing(apps, schema_editor):
    """Reverse migration: remove all seeded records."""
    PlanPricing = apps.get_model('subscriptions', 'PlanPricing')
    PlanPricing.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0010_coupon_new_plan_types'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PlanPricing',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('plan_type', models.CharField(
                    max_length=20,
                    unique=True,
                    choices=[('starter', 'Starter'), ('premium', 'Premium'), ('custom', 'Custom')],
                )),
                ('price_ngn_monthly', models.DecimalField(
                    max_digits=12, decimal_places=2,
                    help_text='NGN price per month (monthly billing)',
                )),
                ('price_ngn_yearly', models.DecimalField(
                    max_digits=12, decimal_places=2,
                    help_text='NGN per-month rate when billed yearly (total = × 12)',
                )),
                ('price_usd_monthly', models.DecimalField(
                    max_digits=10, decimal_places=2,
                    help_text='USD price per month (monthly billing)',
                )),
                ('price_usd_yearly', models.DecimalField(
                    max_digits=10, decimal_places=2,
                    help_text='USD per-month rate when billed yearly (total = × 12)',
                )),
                ('is_active', models.BooleanField(default=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='pricing_changes',
                    to=settings.AUTH_USER_MODEL,
                    help_text='The admin who last modified this pricing record',
                )),
            ],
            options={
                'verbose_name': 'Plan Pricing',
                'verbose_name_plural': 'Plan Pricing',
                'ordering': ['plan_type'],
            },
        ),
        # Seed initial prices immediately after table creation
        migrations.RunPython(seed_plan_pricing, remove_plan_pricing),
    ]
