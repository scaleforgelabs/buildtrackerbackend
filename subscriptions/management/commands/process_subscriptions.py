from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from subscriptions.models import Subscription, PaymentHistory
from subscriptions.utils import charge_paystack_authorization, charge_flutterwave_token, get_plan_price
from core.messaging import send_dual_notification, send_beautiful_email
import datetime

class Command(BaseCommand):
    help = 'Process recurring subscriptions, retries, and scheduled changes'

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting subscription processing...")
        self.process_expirations_and_changes()
        self.process_due_subscriptions()
        self.process_retries()
        self.send_grace_period_reminder()
        self.notify_expiring_custom()
        self.stdout.write("Subscription processing complete.")

    def process_expirations_and_changes(self):
        """Handle subscriptions that have reached their end_date"""
        now = timezone.now()
        # Find subscriptions past end_date that are active or past_due, 
        # but NOT those in grace period (grace period handled separately or they have grace_period_end)
        # Actually, if they are in grace period, end_date passed but we are giving them time.
        # This function handles EXPLICIT cancellations or downgrades scheduled for period end.
        
        # We look for subscriptions where end_date < now
        # And either cancel_at_period_end is True OR next_plan_type is Set.
        
        # Note: In standard flow, end_date might be passed, but if it's recurring, we typically extend it BEFORE it expires if charge succeeds.
        # If charge failed, it enters grace period.
        # So this function is mainly for:
        # 1. Users who requested CANCEL.
        # 2. Users who requested DOWNGRADE.
        
        expiring_subs = Subscription.objects.filter(
            end_date__lte=now,
            status__in=['active', 'past_due']
        )
        
        for sub in expiring_subs:
            # Case 1: Cancellation Requested
            if sub.cancel_at_period_end:
                self.stdout.write(f"Cancelling subscription for {sub.organization.name}")
                sub.status = 'cancelled'
                sub.plan_type = 'free' # Effectively downgrade to free
                sub.cancel_at_period_end = False
                sub.save()
                
                # Sync Organization
                sub.organization.plan_type = 'free'
                sub.organization.save()
                if sub.organization.owner:
                     sub.organization.owner.plan_type = 'free'
                     sub.organization.owner.save()
                
                self.send_notification(sub, "Subscription Cancelled", "Your subscription has been cancelled as requested.")
                continue

            # Case 2: Scheduled Plan Change (Downgrade)
            if sub.next_plan_type:
                self.stdout.write(f"Applying scheduled plan change for {sub.organization.name}: {sub.plan_type} -> {sub.next_plan_type}")
                old_plan = sub.plan_type
                sub.plan_type = sub.next_plan_type
                sub.next_plan_type = None
                
                if sub.plan_type == 'free':
                    # Downgrade to free: stop billing
                    sub.status = 'active'
                    sub.next_billing_date = None
                    sub.authorization_code = None
                else:
                    # Downgrade to another paid plan (e.g., business -> pro)
                    # We only update the plan_type here. We do NOT push dates forward yet.
                    # The very next method `process_due_subscriptions` relies on the
                    # current `next_billing_date` being in the past/now to trigger the actual charge.
                    sub.status = 'active'
                
                sub.save()
                
                # Sync Org
                sub.organization.plan_type = sub.plan_type
                sub.organization.save()
                if sub.organization.owner:
                     sub.organization.owner.plan_type = sub.plan_type
                     sub.organization.owner.save()

                self.send_notification(sub, "Plan Changed", f"Your plan has been changed from {old_plan} to {sub.plan_type}.")
                continue

    def process_due_subscriptions(self):
        """Attempt to charge subscriptions due for renewal"""
        now = timezone.now()
        # Find active subscriptions due for billing, NOT in grace period, and NOT cancelled
        due_subs = Subscription.objects.filter(
            status='active',
            next_billing_date__lte=now,
            is_in_grace_period=False,
            cancel_at_period_end=False,
            next_plan_type__isnull=True, # No pending changes
            plan_type__in=['starter', 'premium', 'pro', 'business', 'enterprise'] # Only auto-billing paid plans (custom is manual/invoice)
        )

        for sub in due_subs:
            self.stdout.write(f"Processing renewal for {sub.organization.name}")
            self.stdout.write(f"  Provider: {sub.payment_provider}")
            self.stdout.write(f"  Auth Code: {sub.authorization_code}")
            self.stdout.write(f"  Billing Email: {sub.billing_email}")
            self.stdout.write(f"  Owner Email: {sub.organization.owner.email}")
            
            if not sub.authorization_code:
                # No card on file? Enter grace period immediately
                self.stdout.write("  -> No authorization code, entering grace period")
                self.enter_grace_period(sub)
                continue

            amount = get_plan_price(sub.plan_type, 'NGN') # Default currency
            charge_email = sub.billing_email or sub.organization.owner.email
            self.stdout.write(f"  Charging {amount} NGN to {charge_email}")
            
            success = False
            data = None
            
            if sub.payment_provider == 'paystack':
                 success, data = charge_paystack_authorization(amount, charge_email, sub.authorization_code)
            elif sub.payment_provider == 'flutterwave':
                 success, data = charge_flutterwave_token(amount, charge_email, sub.authorization_code)
            
            self.stdout.write(f"  Charge result: success={success}, data={data}")
            
            if success:
                self.handle_successful_renewal(sub, amount, data)
            else:
                self.enter_grace_period(sub)

    def process_retries(self):
        """Retry failed subscriptions in grace period"""
        now = timezone.now()
        # Find subscriptions in grace period where retry date has come
        retry_subs = Subscription.objects.filter(
            is_in_grace_period=True,
            next_retry_date__lte=now,
            status__in=['active', 'past_due'] 
        )

        for sub in retry_subs:
            self.stdout.write(f"Retrying payment for {sub.organization.name} (Attempt {sub.retry_count + 1}/3)")
            
            if not sub.authorization_code:
                self.downgrade_due_to_failure(sub)
                continue

            # Increment retry count
            sub.retry_count += 1
            
            # Check if max retries exceeded (3 attempts)
            if sub.retry_count > 3:
                self.stdout.write(f"Max retries exceeded for {sub.organization.name}")
                self.downgrade_due_to_failure(sub)
                continue

            amount = get_plan_price(sub.plan_type, 'NGN')
            success = False
            data = None
            
            if sub.payment_provider == 'paystack':
                 success, data = charge_paystack_authorization(amount, sub.billing_email or sub.organization.owner.email, sub.authorization_code)
            elif sub.payment_provider == 'flutterwave':
                 success, data = charge_flutterwave_token(amount, sub.billing_email or sub.organization.owner.email, sub.authorization_code)
            
            if success:
                self.handle_successful_renewal(sub, amount, data)
            else:
                # Retry Failed
                if sub.retry_count >= 3:
                    # Final retry failed, downgrade
                    self.downgrade_due_to_failure(sub)
                else:
                    # Schedule next retry (every 2 days)
                    sub.next_retry_date = timezone.now() + datetime.timedelta(days=2)
                    sub.save()
                    self.send_notification(
                        sub,
                        f"Payment Retry Failed (Attempt {sub.retry_count}/3)",
                        "We attempted to charge your card but it failed. We will retry in 2 days. Please update your payment method to avoid service interruption."
                    )

    def handle_successful_renewal(self, sub, amount, data):
        self.stdout.write(f"Renewal successful for {sub.organization.name}")
        
        # 1. Update Subscription
        sub.status = 'active'
        sub.is_in_grace_period = False
        sub.retry_count = 0
        sub.last_charged_date = timezone.now()
        
        # Extend dates
        # If it was past due, do we extend from NOW or from old end_date?
        # Usually from standard end_date to keep cycles aligned, but if gap is large, maybe FROM NOW.
        # Let's extend from expected end_date to keep cycle anchor, unless it's way in past.
        # For simplicity, extend from NOW if it was expired, or add 30 days.
        days_to_add = 365 if sub.billing_cycle == 'yearly' else 30
        sub.end_date = timezone.now() + datetime.timedelta(days=days_to_add)
        sub.next_billing_date = sub.end_date
        sub.grace_period_end = sub.end_date + datetime.timedelta(days=3)
        sub.save()

        # 2. Log Payment
        PaymentHistory.objects.create(
            organization=sub.organization,
            amount=amount,
            currency='NGN',
            payment_provider=sub.payment_provider,
            reference=data.get('reference', f'recur_{timezone.now().timestamp()}'),
            status='success',
            plan_type=sub.plan_type,
            metadata={'type': 'recurring_renewal'}
        )
        
        self.send_notification(sub, "Subscription Renewed", "Your subscription has been successfully renewed.")

    def enter_grace_period(self, sub):
        self.stdout.write(f"Payment failed for {sub.organization.name}, entering grace period")
        sub.is_in_grace_period = True
        sub.status = 'past_due'
        sub.retry_count = 0  # Reset retry count
        sub.next_retry_date = timezone.now() + datetime.timedelta(days=3)
        sub.grace_period_end = timezone.now() + datetime.timedelta(days=7)  # 7-day grace period
        sub.save()
        
        # First reminder notification
        self.send_notification(
            sub,
            "Payment Failed - Grace Period Started",
            f"Your payment for the {sub.plan_type} plan failed. We will retry in 3 days. Please update your payment method to avoid service interruption. You have 7 days before your account is downgraded to the free plan."
        )
    
    def send_grace_period_reminder(self):
        """Send second reminder email to subscriptions nearing end of grace period"""
        now = timezone.now()
        # Find subscriptions in grace period with 1-2 days remaining
        reminder_threshold = now + datetime.timedelta(days=2)
        
        subs_needing_reminder = Subscription.objects.filter(
            is_in_grace_period=True,
            grace_period_end__lte=reminder_threshold,
            grace_period_end__gt=now,
            status='past_due'
        )
        
        for sub in subs_needing_reminder:
            days_remaining = (sub.grace_period_end - now).days
            self.stdout.write(f"Sending final reminder to {sub.organization.name}")
            self.send_notification(
                sub,
                "URGENT: Grace Period Ending Soon",
                f"Your grace period ends in {days_remaining} day(s). Please update your payment method immediately to avoid being downgraded to the free plan."
            )

    def downgrade_due_to_failure(self, sub):
        self.stdout.write(f"Grace period ended for {sub.organization.name}, downgrading.")
        old_plan = sub.plan_type
        sub.plan_type = 'free'
        sub.status = 'active' # Free is active
        sub.is_in_grace_period = False
        sub.retry_count = 0
        sub.authorization_code = None
        sub.next_billing_date = None
        sub.save()
        
        # Sync Org
        sub.organization.plan_type = 'free'
        sub.organization.save()
        if sub.organization.owner:
             sub.organization.owner.plan_type = 'free'
             sub.organization.owner.save()

        self.send_notification(sub, "Subscription Cancelled", f"We could not process your payment for {old_plan}. You have been downgraded to the Free plan.")

    def notify_expiring_custom(self):
        """
        Email the admin when a custom plan is 30, 14, or 7 days from expiry.
        Custom plans are manually invoiced so they need a heads-up to generate
        a renewal payment link before the subscription lapses.
        """
        from django.conf import settings as djsettings
        from core.messaging import send_beautiful_email

        now = datetime.datetime.now(datetime.timezone.utc)
        admin_email = getattr(djsettings, 'ADMIN_EMAIL', None) or getattr(djsettings, 'DEFAULT_FROM_EMAIL', None)

        for days in [30, 14, 7]:
            window_start = now + datetime.timedelta(days=days - 1)
            window_end   = now + datetime.timedelta(days=days)

            expiring = Subscription.objects.filter(
                plan_type='custom',
                status='active',
                end_date__gte=window_start,
                end_date__lt=window_end,
            ).select_related('organization', 'organization__owner')

            for sub in expiring:
                expiry_str = sub.end_date.strftime('%B %d, %Y') if sub.end_date else 'unknown'
                org_name   = sub.organization.name if sub.organization else 'Unknown Org'
                owner_email = (
                    sub.organization.owner.email
                    if sub.organization and sub.organization.owner
                    else None
                )

                self.stdout.write(
                    f"[Custom expiry] {org_name} expires in {days} day(s) ({expiry_str})"
                )

                # Notify the organisation owner
                self.send_notification(
                    sub,
                    f"Your BuildTracker Custom Plan expires in {days} day(s)",
                    (
                        f"Your Custom plan for {org_name} is set to expire on {expiry_str}. "
                        f"Please contact us to renew your subscription and avoid any interruption."
                    ),
                )

                # Also notify the platform admin so they can generate a renewal link
                if admin_email:
                    try:
                        send_beautiful_email(
                            subject=f"[Action Required] {org_name} custom plan expires in {days} day(s)",
                            message=(
                                f"{org_name}'s custom subscription expires on {expiry_str} "
                                f"({days} day(s) from now).\n\n"
                                f"Owner: {owner_email or 'unknown'}\n\n"
                                f"Go to the Revenue page in the admin dashboard to generate "
                                f"a renewal payment link."
                            ),
                            recipient_list=[admin_email],
                            fail_silently=True,
                        )
                    except Exception:
                        pass

    def send_notification(self, sub, subject, message):
        """Send dual notification to organization owner"""
        if sub.organization and sub.organization.owner:
            send_dual_notification(
                user=sub.organization.owner,
                subject=subject,
                message=message,
                fail_silently=True
            )
        else:
            # Fallback for cases where owner might be missing (shouldn't happen)
            send_beautiful_email(
                subject=subject,
                message=message,
                recipient_list=[sub.billing_email or sub.organization.owner.email],
                fail_silently=True,
            )
