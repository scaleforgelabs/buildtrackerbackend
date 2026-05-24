import logging
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
import re

logger = logging.getLogger(__name__)

BRAND_BLUE        = '#4372E9'
BRAND_BLUE_BG     = '#EFF4FF'
BRAND_BLUE_BORDER = '#C7D7FD'

# Per-type chip labels — all use brand blue except hard semantic red (danger) actions
EMAIL_TYPE_META = {
    'task_assigned':    {'color': BRAND_BLUE,  'bg': BRAND_BLUE_BG,  'border': BRAND_BLUE_BORDER, 'chip': 'Task Assigned'},
    'status_update':    {'color': BRAND_BLUE,  'bg': BRAND_BLUE_BG,  'border': BRAND_BLUE_BORDER, 'chip': 'Status Update'},
    'comment':          {'color': BRAND_BLUE,  'bg': BRAND_BLUE_BG,  'border': BRAND_BLUE_BORDER, 'chip': 'New Comment'},
    'blocker':          {'color': '#EF4444',   'bg': '#FEF2F2',      'border': '#FECACA',          'chip': 'Blocker Reported'},
    'reminder':         {'color': BRAND_BLUE,  'bg': BRAND_BLUE_BG,  'border': BRAND_BLUE_BORDER, 'chip': 'Due Date Reminder'},
    'daily_summary':    {'color': BRAND_BLUE,  'bg': BRAND_BLUE_BG,  'border': BRAND_BLUE_BORDER, 'chip': 'Daily Summary'},
    'wiki_create':      {'color': BRAND_BLUE,  'bg': BRAND_BLUE_BG,  'border': BRAND_BLUE_BORDER, 'chip': 'Wiki — New Document'},
    'wiki_update':      {'color': BRAND_BLUE,  'bg': BRAND_BLUE_BG,  'border': BRAND_BLUE_BORDER, 'chip': 'Wiki — Updated'},
    'wiki_delete':      {'color': '#EF4444',   'bg': '#FEF2F2',      'border': '#FECACA',          'chip': 'Wiki — Deleted'},
    'invitation':       {'color': BRAND_BLUE,  'bg': BRAND_BLUE_BG,  'border': BRAND_BLUE_BORDER, 'chip': "You're Invited"},
    'member_joined':    {'color': BRAND_BLUE,  'bg': BRAND_BLUE_BG,  'border': BRAND_BLUE_BORDER, 'chip': 'Team Update'},
    'deletion':         {'color': '#EF4444',   'bg': '#FEF2F2',      'border': '#FECACA',          'chip': 'Task Deleted'},
    'general_update':   {'color': BRAND_BLUE,  'bg': BRAND_BLUE_BG,  'border': BRAND_BLUE_BORDER, 'chip': 'Task Updated'},
    'usage_alert':      {'color': BRAND_BLUE,  'bg': BRAND_BLUE_BG,  'border': BRAND_BLUE_BORDER, 'chip': 'Usage Alert'},
}
_DEFAULT_META = {'color': BRAND_BLUE, 'bg': BRAND_BLUE_BG, 'border': BRAND_BLUE_BORDER, 'chip': None}


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
            from_email='BuildTracker <noreply@buildtrackerapp.com>',
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
