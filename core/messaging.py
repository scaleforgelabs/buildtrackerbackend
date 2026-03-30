import logging
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
import re

logger = logging.getLogger(__name__)

def send_beautiful_email(subject, message, recipient_list, fail_silently=False):
    """
    Sends a beautifully formatted HTML email, falling back to plain text.
    """
    action_url = None
    action_text = "View Details"
    
    task_match = re.search(r'View (task|review|workspace|ticket):\s*(https?://[^\s]+)', message, re.IGNORECASE)
    if task_match:
        action_text = f"View {task_match.group(1).capitalize()}"
        action_url = task_match.group(2)
        message = message.replace(task_match.group(0), "").strip()
    else:
        invite_match = re.search(r'(?:Click the link below to accept the invitation|accept the invitation):\s*(https?://[^\s]+)', message, re.IGNORECASE)
        if invite_match:
            action_text = "Accept Invitation"
            action_url = invite_match.group(1)
            message = message.replace(invite_match.group(0), "").strip()

    try:
        html_content = render_to_string('core/base_email.html', {
            'subject': subject,
            'message': message,
            'action_url': action_url,
            'action_text': action_text
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
