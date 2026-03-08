from celery import shared_task
from django.core.management import call_command
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

@shared_task
def process_subscriptions_task():
    """
    Celery task to process subscription renewals, retries, and scheduled changes.
    Runs daily to handle:
    - Recurring billing charges
    - Grace period retries
    - Scheduled cancellations/downgrades
    """
    try:
        logger.info("Starting automated subscription processing...")
        call_command('process_subscriptions')
        logger.info("Subscription processing completed successfully")
    except Exception as e:
        logger.error(f"Error processing subscriptions: {str(e)}")
        raise

@shared_task
def process_paystack_webhook_task(event, data):
    from .models import PaymentHistory, Subscription, PaymentMethod
    
    if event == 'charge.success':
        reference = data.get('reference')
        try:
            payment = PaymentHistory.objects.get(reference=reference)
            if payment.status != 'success':
                # SECURITY CHECK: Verify Amount
                from decimal import Decimal
                amount_kobo = data.get('amount', 0)
                paid_amount = Decimal(amount_kobo) / Decimal(100)
                
                if paid_amount < payment.amount:
                    msg = f"Potential Fraud Attempt (Webhook): Amount mismatch. Ref: {reference}, Expected: {payment.amount}, Paid: {paid_amount}"
                    logger.warning(msg)
                    
                    payment.status = 'failed'
                    payment.metadata['failure_reason'] = msg
                    payment.save()
                    return

                payment.status = 'success'
                payment.save()

                organization = payment.organization
                organization.plan_type = payment.plan_type
                organization.save()

                if organization.owner:
                    organization.owner.plan_type = payment.plan_type
                    organization.owner.save()

                auth_code = data.get('authorization', {}).get('authorization_code')
                sub_code = data.get('subscription_code')
                email_token = data.get('email_token')
                
                existing_sub = Subscription.objects.filter(organization=organization).first()
                
                days_to_add = 365 if payment.billing_cycle == 'yearly' else 30
                
                if existing_sub and existing_sub.end_date and existing_sub.end_date > timezone.now() and existing_sub.status in ('active', 'past_due'):
                    base_date = existing_sub.end_date
                else:
                    base_date = timezone.now()
                    
                new_end_date = base_date + timezone.timedelta(days=days_to_add)

                Subscription.objects.update_or_create(
                    organization=organization,
                    defaults={
                        'plan_type': payment.plan_type,
                        'billing_cycle': payment.billing_cycle,
                        'status': 'active',
                        'payment_provider': 'paystack',
                        'end_date': new_end_date,
                        'next_billing_date': new_end_date,
                        'grace_period_end': new_end_date + timezone.timedelta(days=3), # 3 days grace
                        'authorization_code': auth_code,
                        'subscription_code': sub_code,
                        'email_token': email_token,
                        'cancel_at_period_end': False,
                        'next_plan_type': None,
                        'is_in_grace_period': False,
                        'retry_count': 0
                    }
                )
        except PaymentHistory.DoesNotExist:
            logger.error(f"Paystack Webhook: Payment ref {reference} not found.")

    elif event == 'charge.failed':
        reference = data.get('reference')
        try:
            payment = PaymentHistory.objects.get(reference=reference)
            payment.status = 'failed'
            payment.save()

            # Find subscription and enter grace period if active
            organization = payment.organization
            try:
                sub = organization.subscription
                if sub.status == 'active':
                    from .management.commands.process_subscriptions import Command as SubCommand
                    cmd = SubCommand()
                    cmd.enter_grace_period(sub)
            except Subscription.DoesNotExist:
                pass
        except PaymentHistory.DoesNotExist:
            logger.error(f"Paystack Webhook: Failed Payment ref {reference} not found.")

@shared_task
def process_flutterwave_webhook_task(event, data):
    from .models import PaymentHistory, Subscription, PaymentMethod
    
    if event == 'charge.completed' and data.get('status') == 'successful':
        tx_ref = data.get('tx_ref')
        try:
            payment = PaymentHistory.objects.get(reference=tx_ref)
            if payment.status != 'success':
                from decimal import Decimal
                paid_amount = Decimal(str(data.get('amount', 0))) 
                
                if paid_amount < payment.amount:
                    msg = f"Potential Fraud Attempt (Webhook): Amount mismatch. Ref: {tx_ref}, Expected: {payment.amount}, Paid: {paid_amount}"
                    logger.warning(msg)

                    payment.status = 'failed'
                    payment.metadata['failure_reason'] = msg
                    payment.save()
                    return

                payment.status = 'success'
                payment.save()

                auth_code = data.get('card', {}).get('token')
                if not auth_code:
                     auth_code = data.get('token')
                if not auth_code and 'data' in data:
                     auth_code = data.get('data', {}).get('card', {}).get('token')
                     if not auth_code:
                          auth_code = data.get('data', {}).get('token')
                     
                sub_id = data.get('id')
                if not sub_id and 'data' in data:
                     sub_id = data.get('data', {}).get('id')
                sub_code = str(sub_id) if sub_id else data.get('tx_ref')
                
                billing_email = data.get('customer', {}).get('email')
                if not billing_email and 'data' in data:
                     billing_email = data.get('data', {}).get('customer', {}).get('email')
                
                fw_card = data.get('card', {})
                if not fw_card and 'data' in data:
                    fw_card = data.get('data', {}).get('card', {})
                card_last4 = fw_card.get('last_4digits')
                card_type = (fw_card.get('type') or fw_card.get('issuer', '')).upper()
                card_first6 = fw_card.get('first_6digits')
                card_expiry = fw_card.get('expiry')
                
                new_plan = payment.plan_type
                existing_sub = Subscription.objects.filter(organization=organization).first()
                
                organization.plan_type = new_plan
                organization.save()
                if organization.owner:
                    organization.owner.plan_type = new_plan
                    organization.owner.save()
                
                days_to_add = 365 if payment.billing_cycle == 'yearly' else 30
                
                if existing_sub and existing_sub.end_date and existing_sub.end_date > timezone.now() and existing_sub.status in ('active', 'past_due'):
                    base_date = existing_sub.end_date
                else:
                    base_date = timezone.now()
                    
                new_end_date = base_date + timezone.timedelta(days=days_to_add)

                Subscription.objects.update_or_create(
                    organization=organization,
                    defaults={
                        'plan_type': payment.plan_type,
                        'billing_cycle': payment.billing_cycle,
                        'status': 'active',
                        'payment_provider': 'flutterwave',
                        'end_date': new_end_date,
                        'next_billing_date': new_end_date,
                        'grace_period_end': new_end_date + timezone.timedelta(days=3),
                        'authorization_code': auth_code,
                        'subscription_code': sub_code,
                        'email_token': None,
                        'billing_email': billing_email,
                        'cancel_at_period_end': False,
                        'next_plan_type': None,
                        'is_in_grace_period': False,
                        'retry_count': 0
                    }
                )
                
                if card_last4:
                    pm, _ = PaymentMethod.objects.update_or_create(
                        organization=organization,
                        provider='flutterwave',
                        card_last4=card_last4,
                        defaults={
                            'card_type': card_type or '',
                            'card_expiry': card_expiry or '',
                            'card_first6': card_first6 or '',
                            'is_default': True,
                        }
                    )
                    PaymentMethod.objects.filter(organization=organization).exclude(id=pm.id).update(is_default=False)
                    old_pms = PaymentMethod.objects.filter(organization=organization).order_by('-updated_at')[3:]
                    PaymentMethod.objects.filter(id__in=[p.id for p in old_pms]).delete()
        except PaymentHistory.DoesNotExist:
            logger.error(f"Flutterwave Webhook: Payment ref {tx_ref} not found.")

    elif event == 'charge.completed' and data.get('status') == 'failed':
        tx_ref = data.get('tx_ref')
        try:
            payment = PaymentHistory.objects.get(reference=tx_ref)
            payment.status = 'failed'
            payment.save()

            organization = payment.organization
            try:
                sub = organization.subscription
                if sub.status == 'active':
                    from .management.commands.process_subscriptions import Command as SubCommand
                    cmd = SubCommand()
                    cmd.enter_grace_period(sub)
            except Subscription.DoesNotExist:
                pass
        except PaymentHistory.DoesNotExist:
            logger.error(f"Flutterwave Webhook: Failed Payment ref {tx_ref} not found.")
