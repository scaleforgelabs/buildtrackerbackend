import logging
import re
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

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


def send_whatsapp_message(phone, user_name, body, action_url=None, fail_silently=True):
    """
    Send a WhatsApp notification via Meta WhatsApp Business Cloud API.

    Template setup (create once in Meta Business Manager):

    Template 1 — for task notifications (has "Open Task" button):
      Name:     buildtracker_task_notification   (or WHATSAPP_TEMPLATE_TASK env var)
      Category: UTILITY
      Body:     Hi {{1}}, 👋\n\n{{2}}
      Button:   URL → "Open Task" → https://your-app.com/{{1}}

    Template 2 — for plain notifications (no button):
      Name:     buildtracker_notification   (or WHATSAPP_TEMPLATE_PLAIN env var)
      Category: UTILITY
      Body:     Hi {{1}}, 👋\n\n{{2}}

    Required env vars:
      WHATSAPP_ACCESS_TOKEN      – Permanent token from Meta Developer Console
      WHATSAPP_PHONE_NUMBER_ID   – Phone Number ID from WhatsApp API Setup page
    """
    import requests as http

    access_token    = getattr(settings, 'WHATSAPP_ACCESS_TOKEN', '')
    phone_number_id = getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '')
    api_version     = getattr(settings, 'WHATSAPP_API_VERSION', 'v19.0')
    task_template   = getattr(settings, 'WHATSAPP_TEMPLATE_TASK', 'buildtracker_task_notification')
    plain_template  = getattr(settings, 'WHATSAPP_TEMPLATE_PLAIN', 'buildtracker_notification')

    if not access_token or not phone_number_id:
        logger.warning("WhatsApp credentials not configured (WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID). Skipping.")
        return False

    # Normalise phone to E.164 format (+countrycode...)
    phone = phone.strip().replace(' ', '').replace('-', '')
    if phone.startswith('0'):
        phone = f'+234{phone[1:]}'   # Default to Nigeria — adjust if needed
    elif not phone.startswith('+'):
        phone = f'+{phone}'

    api_url = f'https://graph.facebook.com/{api_version}/{phone_number_id}/messages'
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }

    if action_url:
        # Task notification template with "Open Task" CTA button.
        # The button URL in Meta is set as: https://your-app.com/{{1}}
        # We pass the path suffix (everything after the domain) as the variable.
        frontend_url = getattr(settings, 'FRONTEND_URL', '').rstrip('/')
        url_suffix = action_url[len(frontend_url):].lstrip('/') if action_url.startswith(frontend_url) else action_url

        payload = {
            'messaging_product': 'whatsapp',
            'to': phone,
            'type': 'template',
            'template': {
                'name': task_template,
                'language': {'code': 'en_US'},
                'components': [
                    {
                        'type': 'body',
                        'parameters': [
                            {'type': 'text', 'text': user_name},
                            {'type': 'text', 'text': body},
                        ],
                    },
                    {
                        'type': 'button',
                        'sub_type': 'url',
                        'index': '0',
                        'parameters': [
                            {'type': 'text', 'text': url_suffix},
                        ],
                    },
                ],
            },
        }
    else:
        # Plain notification template (no button).
        payload = {
            'messaging_product': 'whatsapp',
            'to': phone,
            'type': 'template',
            'template': {
                'name': plain_template,
                'language': {'code': 'en_US'},
                'components': [
                    {
                        'type': 'body',
                        'parameters': [
                            {'type': 'text', 'text': user_name},
                            {'type': 'text', 'text': body},
                        ],
                    },
                ],
            },
        }

    try:
        response = http.post(api_url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            logger.info(f"WhatsApp message sent to {phone}")
            return True
        else:
            logger.error(f"WhatsApp API error {response.status_code}: {response.text}")
            if not fail_silently:
                raise Exception(f"WhatsApp API error {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"WhatsApp send error for {phone}: {e}")
        if not fail_silently:
            raise
        return False


def send_dual_notification(user, subject, message, fail_silently=False, extra_context=None):
    """
    Sends notification via Email + WhatsApp using a background task.
    WhatsApp is only sent if the user has a phone number on their profile.
    """
    from core.tasks import send_dual_notification_task
    send_dual_notification_task.delay(user.id, subject, message, fail_silently, extra_context or {})
