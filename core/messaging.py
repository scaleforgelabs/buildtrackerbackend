import logging
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

logger = logging.getLogger(__name__)

def send_beautiful_email(subject, message, recipient_list, fail_silently=False):
    """
    Sends a beautifully formatted HTML email, falling back to plain text.
    """
    try:
        html_content = render_to_string('core/base_email.html', {
            'subject': subject,
            'message': message,
        })
        email = EmailMultiAlternatives(
            subject=subject,
            body=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipient_list,
        )
        email.attach_alternative(html_content, "text/html")
        return email.send(fail_silently=fail_silently)
    except Exception as e:
        logger.error(f"Error sending HTML email to {recipient_list}: {str(e)}")
        if not fail_silently:
            raise
        return 0

def send_dual_notification(user, subject, message, fail_silently=False):
    """
    Sends notification via both Email and SMS (Twilio) using a background task.
    """
    from core.tasks import send_dual_notification_task
    send_dual_notification_task.delay(user.id, subject, message, fail_silently)
