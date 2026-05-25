from rest_framework import serializers
from .models import Subscription, PaymentHistory

class PlanSerializer(serializers.Serializer):
    type = serializers.CharField()
    name = serializers.CharField()
    price_naira = serializers.DecimalField(max_digits=10, decimal_places=2)
    price_usd = serializers.DecimalField(max_digits=10, decimal_places=2)
    limits = serializers.DictField()
    features = serializers.ListField(child=serializers.CharField())

class SubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source='get_plan_type_display', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)

    class Meta:
        model = Subscription
        fields = ['id', 'organization', 'organization_name', 'plan_type', 'plan_name', 
                  'status', 'start_date', 'end_date', 'payment_provider']
        read_only_fields = ['organization', 'status', 'start_date', 'end_date']

class InitiateSubscriptionSerializer(serializers.Serializer):
    plan_type = serializers.ChoiceField(choices=[
        # Current plan names
        ('starter',    'Starter Plan'),
        ('premium',    'Premium Plan'),
        ('custom',     'Custom Plan'),
        # Legacy aliases (kept for backward-compat with existing integrations)
        ('pro',        'Pro Plan (Legacy)'),
        ('business',   'Business Plan (Legacy)'),
        ('enterprise', 'Enterprise Plan (Legacy)'),
    ])
    payment_provider = serializers.ChoiceField(choices=[
        ('paystack', 'Paystack'),
        ('flutterwave', 'Flutterwave')
    ])
    currency = serializers.ChoiceField(choices=[('NGN', 'NGN'), ('USD', 'USD')], default='NGN')
    billing_cycle = serializers.ChoiceField(choices=[('monthly', 'Monthly'), ('yearly', 'Yearly')], default='monthly')
    callback_url = serializers.URLField(required=False)
    coupon_code = serializers.CharField(required=False, allow_blank=True, help_text="Optional coupon code for a discount")

class PaymentHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentHistory
        fields = '__all__'
class VerifyPaymentSerializer(serializers.Serializer):
    reference = serializers.CharField(required=True)
    provider = serializers.ChoiceField(choices=[('paystack', 'Paystack'), ('flutterwave', 'Flutterwave')], required=True)
    transaction_id = serializers.CharField(required=False, help_text="Required for Flutterwave verification if reference is not sufficient")
