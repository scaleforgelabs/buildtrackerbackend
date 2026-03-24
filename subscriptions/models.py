from django.db import models
from organizations.models import Organization
import uuid

class Subscription(models.Model):
    PLAN_CHOICES = [
        ('free', 'Starter Plan'),
        ('pro', 'Pro Plan'),
        ('business', 'Business Plan'),
        ('enterprise', 'Enterprise Plan'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('cancelled', 'Cancelled'),
        ('past_due', 'Past Due'),
    ]

    PAYMENT_PROVIDER_CHOICES = [
        ('paystack', 'Paystack'),
        ('flutterwave', 'Flutterwave'),
    ]

    BILLING_CYCLE_CHOICES = [
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name='subscription')
    plan_type = models.CharField(max_length=20, choices=PLAN_CHOICES, default='free')
    billing_cycle = models.CharField(max_length=20, choices=BILLING_CYCLE_CHOICES, default='monthly')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(null=True, blank=True)
    grace_period_end = models.DateTimeField(null=True, blank=True, help_text="End of grace period after subscription expiry")
    payment_provider = models.CharField(max_length=20, choices=PAYMENT_PROVIDER_CHOICES, null=True, blank=True)
    subscription_code = models.CharField(max_length=100, null=True, blank=True, help_text="Subscription code from payment provider")
    email_token = models.CharField(max_length=100, null=True, blank=True, help_text="Email token for managing subscription")
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Recurring Billing Fields
    authorization_code = models.CharField(max_length=100, null=True, blank=True, help_text="Token for recurring charges")
    billing_email = models.EmailField(null=True, blank=True, help_text="Email used from the payment gateway associated with the token")
    email_token = models.CharField(max_length=100, null=True, blank=True)
    
    
    # Grace Period Logic
    is_in_grace_period = models.BooleanField(default=False)
    retry_count = models.IntegerField(default=0)
    next_retry_date = models.DateTimeField(null=True, blank=True)

    # Scheduled Changes (Decision Flow)
    cancel_at_period_end = models.BooleanField(default=False, help_text="If True, subscription cancels after end_date")
    next_plan_type = models.CharField(max_length=20, null=True, blank=True, choices=PLAN_CHOICES, help_text="Plan to switch to after end_date")

    # Timing
    last_charged_date = models.DateTimeField(null=True, blank=True)
    next_billing_date = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        from datetime import timedelta
        from django.utils import timezone

        # If next_billing_date is not set, default it to 30 days from now (or start_date)
        if not self.next_billing_date:
            base_date = self.last_charged_date if self.last_charged_date else timezone.now()
            self.next_billing_date = base_date + timedelta(days=30)
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.organization.name} - {self.plan_type}"

class PaymentHistory(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    PAYMENT_PROVIDER_CHOICES = [
        ('paystack', 'Paystack'),
        ('flutterwave', 'Flutterwave'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='NGN')
    payment_provider = models.CharField(max_length=20, choices=PAYMENT_PROVIDER_CHOICES)
    reference = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    plan_type = models.CharField(max_length=20, null=True, blank=True)
    billing_cycle = models.CharField(max_length=20, choices=Subscription.BILLING_CYCLE_CHOICES, default='monthly')
    transaction_date = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.organization.name} - {self.amount} {self.currency} - {self.status}"

class PaymentMethod(models.Model):
    PROVIDER_CHOICES = [
        ('paystack', 'Paystack'),
        ('flutterwave', 'Flutterwave'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='payment_methods')
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    card_last4 = models.CharField(max_length=4, help_text="Last 4 digits of the card")
    card_type = models.CharField(max_length=20, blank=True, default='', help_text="Card brand e.g. VISA, MASTERCARD")
    card_expiry = models.CharField(max_length=7, blank=True, default='', help_text="Card expiry e.g. 09/32")
    card_first6 = models.CharField(max_length=6, blank=True, default='', help_text="First 6 digits (BIN)")
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        # A card is unique per org + provider + last4
        unique_together = ['organization', 'provider', 'card_last4']

    def __str__(self):
        return f"{self.provider}/{self.card_type} **** {self.card_last4}"
