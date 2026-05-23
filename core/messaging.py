import logging
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
import re

logger = logging.getLogger(__name__)

# Per-type accent colours and chip labels
EMAIL_TYPE_META = {
    'task_assigned':    {'color': '#4372E9', 'bg': '#EFF4FF', 'border': '#C7D7FD', 'chip': 'Task Assigned'},
    'status_update':    {'color': '#F97316', 'bg': '#FFF7ED', 'border': '#FED7AA', 'chip': 'Status Update'},
    'comment':          {'color': '#10B981', 'bg': '#ECFDF5', 'border': '#A7F3D0', 'chip': 'New Comment'},
    'blocker':          {'color': '#EF4444', 'bg': '#FEF2F2', 'border': '#FECACA', 'chip': 'Blocker Reported'},
    'reminder':         {'color': '#F59E0B', 'bg': '#FFFBEB', 'border': '#FDE68A', 'chip': 'Due Date Reminder'},
    'daily_summary':    {'color': '#6366F1', 'bg': '#EEF2FF', 'border': '#C7D2FE', 'chip': 'Daily Summary'},
    'wiki_create':      {'color': '#8B5CF6', 'bg': '#F5F3FF', 'border': '#DDD6FE', 'chip': 'Wiki — New Document'},
    'wiki_update':      {'color': '#0EA5E9', 'bg': '#F0F9FF', 'border': '#BAE6FD', 'chip': 'Wiki — Document Updated'},
    'wiki_delete':      {'color': '#EF4444', 'bg': '#FEF2F2', 'border': '#FECACA', 'chip': 'Wiki — Document Deleted'},
    'invitation':       {'color': '#4372E9', 'bg': '#EFF4FF', 'border': '#C7D7FD', 'chip': 'You\'re Invited'},
    'member_joined':    {'color': '#10B981', 'bg': '#ECFDF5', 'border': '#A7F3D0', 'chip': 'Team Update'},
    'deletion':         {'color': '#EF4444', 'bg': '#FEF2F2', 'border': '#FECACA', 'chip': 'Task Deleted'},
    'general_update':   {'color': '#F97316', 'bg': '#FFF7ED', 'border': '#FED7AA', 'chip': 'Task Updated'},
    'usage_alert':      {'color': '#F59E0B', 'bg': '#FFFBEB', 'border': '#FDE68A', 'chip': 'Usage Alert'},
}
_DEFAULT_META = {'color': '#4372E9', 'bg': '#EFF4FF', 'border': '#C7D7FD', 'chip': None}


def send_beautiful_email(subject, message, recipient_list, fail_silently=False, extra_context=None):
    """
    Sends a beautifully formatted HTML email.

    extra_context keys (all optional):
        email_type      – key from EMAIL_TYPE_META (controls accent colour + chip label)
        recipient_name  – first name shown in "Hi [name],"
        metadata_rows   – list of {'label': str, 'value': str} rendered as a detail table
        action_url      – CTA button link (overrides auto-detected URL from message)
        action_text     – CTA button label
        chip_label      – override the chip text
        accent_color    – override the accent colour directly
    """
    extra_context = extra_context or {}

    # Determine accent colour and chip from email_type
    email_type = extra_context.get('email_type', '')
    type_meta = EMAIL_TYPE_META.get(email_type, _DEFAULT_META)

    accent_color  = extra_context.get('accent_color')  or type_meta['color']
    accent_bg     = type_meta['bg']
    accent_border = type_meta['border']
    chip_label    = extra_context.get('chip_label') or type_meta.get('chip')

    # Action URL — explicit wins, then auto-detect from message text
    action_url  = extra_context.get('action_url')
    action_text = extra_context.get('action_text', 'Open in BuildTracker')

    if not action_url:
        task_match = re.search(r'View (?:task|review|workspace|ticket):\s*(https?://[^\s]+)', message, re.IGNORECASE)
        if task_match:
            action_url  = task_match.group(1)
            action_text = f"View {task_match.group(0).split()[1].capitalize()}"
            message = message.replace(task_match.group(0), '').strip()
        else:
            invite_match = re.search(r'(?:Click the link below to accept the invitation|accept the invitation):\s*(https?://[^\s]+)', message, re.IGNORECASE)
            if invite_match:
                action_url  = invite_match.group(1)
                action_text = 'Accept Invitation'
                message = message.replace(invite_match.group(0), '').strip()

    try:
        html_content = render_to_string('core/base_email.html', {
            'subject':        subject,
            'message':        message,
            'recipient_name': extra_context.get('recipient_name', ''),
            'metadata_rows':  extra_context.get('metadata_rows', []),
            'chip_label':     chip_label,
            'accent_color':   accent_color,
            'accent_bg':      accent_bg,
            'accent_border':  accent_border,
            'action_url':     action_url,
            'action_text':    action_text,
            'frontend_url':   getattr(settings, 'FRONTEND_URL', '#'),
        })
        email = EmailMultiAlternatives(
            subject=subject,
            body=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipient_list,
        )
        email.attach_alternative(html_content, 'text/html')
        return email.send(fail_silently=fail_silently)
    except Exception as e:
        logger.error(f"Error sending HTML email to {recipient_list}: {str(e)}")
        if not fail_silently:
            raise
        return 0


def send_dual_notification(user, subject, message, fail_silently=False, extra_context=None):
    """
    Sends notification via both Email and SMS (Twilio) using a background task.
    """
    from core.tasks import send_dual_notification_task
    send_dual_notification_task.delay(user.id, subject, message, fail_silently, extra_context or {})
