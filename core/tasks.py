from celery import shared_task
from django.core.cache import cache
import time
from core.messaging import send_beautiful_email, send_whatsapp_message
from auth_func.models import CustomUser
import logging

logger = logging.getLogger(__name__)

@shared_task
def process_data(data):
    """Process data asynchronously"""
    # Simulate processing time
    time.sleep(2)
    result = f"Processed: {data}"
    
    # Cache the result
    cache.set(f"processed_{data}", result, timeout=600)
    
    return result

@shared_task
def cleanup_cache():
    """Periodic task to cleanup cache"""
    # This would be a periodic task
    cache.clear()
    return "Cache cleaned up"

@shared_task
def send_email_task(subject, message, recipient_list, fail_silently=False, extra_context=None):
    send_beautiful_email(
        subject=subject,
        message=message,
        recipient_list=recipient_list,
        fail_silently=fail_silently,
        extra_context=extra_context or {},
    )

@shared_task
def send_dual_notification_task(user_id, subject, message, fail_silently=False, extra_context=None):
    try:
        user = CustomUser.objects.get(id=user_id)
    except CustomUser.DoesNotExist:
        logger.error(f"User {user_id} not found for dual notification")
        return

    try:
        email_sent = send_beautiful_email(
            subject=subject,
            message=message,
            recipient_list=[user.email],
            fail_silently=fail_silently,
            extra_context=extra_context or {},
        )
        if email_sent:
            logger.info(f"Email sent successfully to {user.email}")
        else:
            logger.warning(f"Email failed to send to {user.email}")
    except Exception as e:
        logger.error(f"Error sending email to {user.email}: {str(e)}")
        if not fail_silently:
            raise

    # ── WhatsApp notification (paid plans only) ──────────────────────────────
    FREE_PLAN = 'free'
    WHATSAPP_ELIGIBLE_PLANS = {'starter', 'premium', 'custom', 'pro', 'business', 'enterprise'}

    plan = getattr(user, 'plan_type', FREE_PLAN) or FREE_PLAN
    is_eligible = (
        plan in WHATSAPP_ELIGIBLE_PLANS
        or user.is_staff
        or user.is_superuser
    )

    if not is_eligible:
        logger.info(f"User {user.email} is on the free plan. WhatsApp skipped.")
        return

    if not user.phone:
        logger.info(f"User {user.email} has no phone number. WhatsApp skipped.")
        return

    ctx = extra_context or {}
    user_name  = ctx.get('recipient_name') or user.first_name or user.email.split('@')[0]
    action_url = ctx.get('action_url')

    send_whatsapp_message(
        phone=user.phone,
        user_name=user_name,
        body=subject,
        action_url=action_url,
        fail_silently=True,
    )