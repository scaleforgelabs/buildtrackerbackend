"""
Migration: Add Coupon model + new plan type choices (starter, premium, custom).

Data migration: Rename legacy plan values in Subscription and PaymentHistory:
  pro        → starter
  business   → premium
  enterprise → custom
"""
import uuid
from django.db import migrations, models


def rename_plan_types(apps, schema_editor):
    """Migrate existing plan_type values to new canonical names."""
    Subscription = apps.get_model('subscriptions', 'Subscription')
    PaymentHistory = apps.get_model('subscriptions', 'PaymentHistory')

    RENAME_MAP = {
        'pro':        'starter',
        'business':   'premium',
        'enterprise': 'custom',
    }

    for old, new in RENAME_MAP.items():
        Subscription.objects.filter(plan_type=old).update(plan_type=new)
        Subscription.objects.filter(next_plan_type=old).update(next_plan_type=new)
        PaymentHistory.objects.filter(plan_type=old).update(plan_type=new)


def reverse_rename_plan_types(apps, schema_editor):
    """Reverse migration: restore legacy plan names."""
    Subscription = apps.get_model('subscriptions', 'Subscription')
    PaymentHistory = apps.get_model('subscriptions', 'PaymentHistory')

    REVERSE_MAP = {
        'starter': 'pro',
        'premium': 'business',
        'custom':  'enterprise',
    }

    for new, old in REVERSE_MAP.items():
        Subscription.objects.filter(plan_type=new).update(plan_type=old)
        Subscription.objects.filter(next_plan_type=new).update(next_plan_type=old)
        PaymentHistory.objects.filter(plan_type=new).update(plan_type=old)


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0009_alter_paymenthistory_status_and_more'),
    ]

    operations = [
        # 1. Widen plan_type fields to accommodate new values before data migration
        migrations.AlterField(
            model_name='subscription',
            name='plan_type',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('free',       'Free'),
                    ('starter',    'Starter'),
                    ('premium',    'Premium'),
                    ('custom',     'Custom'),
                    ('pro',        'Starter (Legacy)'),
                    ('business',   'Premium (Legacy)'),
                    ('enterprise', 'Custom (Legacy)'),
                ],
                default='free',
            ),
        ),
        migrations.AlterField(
            model_name='subscription',
            name='next_plan_type',
            field=models.CharField(
                max_length=20,
                null=True,
                blank=True,
                choices=[
                    ('free',       'Free'),
                    ('starter',    'Starter'),
                    ('premium',    'Premium'),
                    ('custom',     'Custom'),
                    ('pro',        'Starter (Legacy)'),
                    ('business',   'Premium (Legacy)'),
                    ('enterprise', 'Custom (Legacy)'),
                ],
            ),
        ),
        # 2. Rename existing records
        migrations.RunPython(rename_plan_types, reverse_rename_plan_types),

        # 3. Create Coupon model
        migrations.CreateModel(
            name='Coupon',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)),
                ('code', models.CharField(db_index=True, max_length=50, unique=True,
                                          help_text='The coupon code users enter at checkout')),
                ('discount_type', models.CharField(
                    max_length=20,
                    choices=[
                        ('percentage', 'Percentage (%)'),
                        ('fixed_ngn',  'Fixed NGN Amount'),
                        ('fixed_usd',  'Fixed USD Amount'),
                    ],
                )),
                ('discount_value', models.DecimalField(max_digits=10, decimal_places=2,
                                                       help_text='Percentage (0-100) or fixed amount')),
                ('max_uses', models.IntegerField(default=0, help_text='0 = unlimited')),
                ('used_count', models.IntegerField(default=0)),
                ('valid_from', models.DateTimeField(null=True, blank=True)),
                ('valid_until', models.DateTimeField(null=True, blank=True)),
                ('applicable_plans', models.JSONField(default=list,
                                                      help_text="List of plan types. Empty = all plans.")),
                ('is_active', models.BooleanField(default=True)),
                ('description', models.CharField(max_length=200, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
