from django.db import models
from organizations.models import Organization
import uuid

class Subscription(models.Model):
    PLAN_CHOICES = [
        ('free',       'Free'),
        ('starter',    'Starter'),
        ('premium',    'Premium'),
        ('custom',     'Custom'),
        # Legacy aliases — kept for existing records; UI maps these to new names
        ('pro',        'Starter (Legacy)'),
        ('business',   'Premium (Legacy)'),
        ('enterprise', 'Custom (Legacy)'),
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


class Coupon(models.Model):
    """
    Discount coupon codes.

    Supports:
      - percentage  — e.g. 20% off the final amount
      - fixed_ngn   — e.g. ₦5,000 off
      - fixed_usd   — e.g. $3 off

    applicable_plans: JSON list of plan types this coupon is valid for.
                      Empty list means it applies to all plans.

    max_uses: 0 = unlimited uses.
    """
    DISCOUNT_TYPE_CHOICES = [
        ('percentage', 'Percentage (%)'),
        ('fixed_ngn',  'Fixed NGN Amount'),
        ('fixed_usd',  'Fixed USD Amount'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True,
                            help_text="The coupon code users enter at checkout")
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2,
                                         help_text="Percentage (0-100) or fixed amount")
    max_uses = models.IntegerField(default=0, help_text="0 = unlimited")
    used_count = models.IntegerField(default=0)
    valid_from = models.DateTimeField(null=True, blank=True,
                                      help_text="Leave blank to make valid immediately")
    valid_until = models.DateTimeField(null=True, blank=True,
                                       help_text="Leave blank for no expiry")
    applicable_plans = models.JSONField(default=list,
                                        help_text="List of plan types e.g. ['starter','premium']. Empty = all plans.")
    is_active = models.BooleanField(default=True)
    description = models.CharField(max_length=200, blank=True,
                                   help_text="Internal note about this coupon")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def is_valid(self, plan_type=None):
        """Check if this coupon is currently usable."""
        from django.utils import timezone
        if not self.is_active:
            return False, "Coupon is no longer active"
        if self.max_uses > 0 and self.used_count >= self.max_uses:
            return False, "Coupon has reached its usage limit"
        now = timezone.now()
        if self.valid_from and now < self.valid_from:
            return False, "Coupon is not yet valid"
        if self.valid_until and now > self.valid_until:
            return False, "Coupon has expired"
        if plan_type and self.applicable_plans and plan_type not in self.applicable_plans:
            return False, f"Coupon is not valid for the {plan_type} plan"
        return True, "Valid"

    def apply_discount(self, amount, currency='NGN'):
        """Return the discounted amount after applying this coupon."""
        from decimal import Decimal
        amount = Decimal(str(amount))
        if self.discount_type == 'percentage':
            discount = amount * (Decimal(str(self.discount_value)) / Decimal('100'))
        elif self.discount_type == 'fixed_ngn' and currency == 'NGN':
            discount = Decimal(str(self.discount_value))
        elif self.discount_type == 'fixed_usd' and currency == 'USD':
            discount = Decimal(str(self.discount_value))
        else:
            discount = Decimal('0')
        discounted = max(amount - discount, Decimal('0'))
        return float(discounted), float(discount)

    def __str__(self):
        return f"{self.code} — {self.discount_type} {self.discount_value}"


class PlanPricing(models.Model):
    """
    Admin-configurable plan pricing stored in the database.

    These records override the default prices in constants.py.
    Only the canonical plan types (starter, premium, custom) are stored here.
    Legacy aliases (pro → starter, etc.) are handled in get_plan_price().

    price_ngn_yearly / price_usd_yearly: the per-month rate when billed annually.
    The yearly total charged upfront = yearly_rate × 12.
    """
    PLAN_CHOICES = [
        ('starter', 'Starter'),
        ('premium', 'Premium'),
        ('custom',  'Custom'),
    ]

    plan_type         = models.CharField(max_length=20, choices=PLAN_CHOICES, unique=True)
    price_ngn_monthly = models.DecimalField(max_digits=12, decimal_places=2, help_text="NGN price per month (monthly billing)")
    price_ngn_yearly  = models.DecimalField(max_digits=12, decimal_places=2, help_text="NGN per-month rate when billed yearly (total = × 12)")
    price_usd_monthly = models.DecimalField(max_digits=10, decimal_places=2, help_text="USD price per month (monthly billing)")
    price_usd_yearly  = models.DecimalField(max_digits=10, decimal_places=2, help_text="USD per-month rate when billed yearly (total = × 12)")
    is_active         = models.BooleanField(default=True)
    updated_at        = models.DateTimeField(auto_now=True)
    updated_by        = models.ForeignKey(
        'auth.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='pricing_changes',
        help_text="The admin who last modified this pricing record"
    )

    class Meta:
        ordering = ['plan_type']
        verbose_name = 'Plan Pricing'
        verbose_name_plural = 'Plan Pricing'

    def __str__(self):
        return f"{self.get_plan_type_display()} — ₦{self.price_ngn_monthly}/mo | ${self.price_usd_monthly}/mo"
