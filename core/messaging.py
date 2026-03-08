import logging

logger = logging.getLogger(__name__)

def send_dual_notification(user, subject, message, fail_silently=False):
    """
    Sends notification via both Email and SMS (Twilio) using a background task.
    """
    from core.tasks import send_dual_notification_task
    send_dual_notification_task.delay(user.id, subject, message, fail_silently)
