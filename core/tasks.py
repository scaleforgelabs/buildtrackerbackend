from celery import shared_task
from django.core.cache import cache
import time
from django.core.mail import send_mail
from django.conf import settings
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from auth_func.models import CustomUser
import os
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
def send_email_task(subject, message, recipient_list, fail_silently=False):
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipient_list,
        fail_silently=fail_silently,
    )

@shared_task
def send_dual_notification_task(user_id, subject, message, fail_silently=False):
    try:
        user = CustomUser.objects.get(id=user_id)
    except CustomUser.DoesNotExist:
        logger.error(f"User {user_id} not found for dual notification")
        return

    try:
        email_sent = send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=fail_silently
        )
        if email_sent:
            logger.info(f"Email sent successfully to {user.email}")
        else:
            logger.warning(f"Email failed to send to {user.email}")
    except Exception as e:
        logger.error(f"Error sending email to {user.email}: {str(e)}")
        if not fail_silently:
            raise

    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    from_number = os.getenv('TWILIO_PHONE_NUMBER')

    if not all([account_sid, auth_token, from_number]):
        logger.warning("Twilio credentials missing in environment variables. SMS skipped.")
        return

    if not user.phone:
        logger.info(f"User {user.email} has no phone number. SMS skipped.")
        return

    try:
        client = Client(account_sid, auth_token)
        sms_body = f"{subject}: {message}" if subject else message
        
        phone = user.phone.strip()
        if phone.startswith('+'):
            to_number = phone
        elif phone.startswith('0'):
            to_number = f"+234{phone.lstrip('0')}"
        elif len(phone) > 10 and not phone.startswith('+'):
            to_number = f"+{phone}"
        else:
            to_number = phone
            
        client.messages.create(
            body=sms_body,
            from_=from_number,
            to=to_number
        )
        logger.info(f"SMS sent successfully to {to_number}")
    except TwilioRestException as e:
        logger.error(f"Twilio error sending SMS to {user.phone}: {str(e)}")
        if not fail_silently:
            raise
    except Exception as e:
        logger.error(f"Unexpected error sending SMS to {user.phone}: {str(e)}")
        if not fail_silently:
            raise