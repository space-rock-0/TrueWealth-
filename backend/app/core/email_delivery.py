"""Transactional email over HTTPS for hosts that block SMTP egress."""
import json
import os
import smtplib
import ssl
import urllib.error
import urllib.request
import re
import logging
from email.message import EmailMessage


def inspect_email_sender():
    """Read-only startup diagnostic; never logs keys or sends a message."""
    if os.getenv('EMAIL_PROVIDER') != 'brevo' or not email_configured():
        return
    request = urllib.request.Request('https://api.brevo.com/v3/senders', headers={'api-key': os.environ['BREVO_API_KEY'], 'Accept': 'application/json'})
    logger = logging.getLogger('backend')
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            senders = json.load(response).get('senders', [])
        sender = os.getenv('EMAIL_FROM') or os.getenv('SMTP_FROM') or ''
        active = any(item.get('email', '').lower() == sender.lower() and item.get('active') for item in senders)
        logger.info('Brevo sender verification status: %s', 'verified' if active else 'sender verification required')
    except urllib.error.HTTPError as error:
        try:
            detail = json.load(error)
        except (ValueError, TypeError):
            detail = {}
        message = str(detail.get('message', ''))
        if 'unrecognised IP' in message:
            address = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', message)
            logger.warning('Brevo IP authorization required for backend outbound IP: %s', address.group(0) if address else 'see Render network settings')
        else:
            logger.warning('Brevo sender diagnostic returned HTTP %s. Check the API key and sender configuration.', error.code)
    except (urllib.error.URLError, TimeoutError):
        logger.warning('Brevo sender diagnostic could not reach the email API.')


def email_configured():
    provider = os.getenv('EMAIL_PROVIDER', 'smtp')
    sender = os.getenv('EMAIL_FROM') or os.getenv('SMTP_FROM')
    if not sender:
        return False
    if provider == 'brevo':
        return bool(os.getenv('BREVO_API_KEY'))
    if provider == 'resend':
        return bool(os.getenv('RESEND_API_KEY'))
    return provider == 'smtp' and all(os.getenv(k) for k in ('SMTP_HOST', 'SMTP_USERNAME', 'SMTP_PASSWORD'))


def send_email(recipient, subject, text):
    if not email_configured():
        raise RuntimeError('Email delivery is not configured.')
    provider = os.getenv('EMAIL_PROVIDER', 'smtp')
    sender = os.getenv('EMAIL_FROM') or os.getenv('SMTP_FROM')
    if provider in ('brevo', 'resend'):
        if provider == 'brevo':
            url = 'https://api.brevo.com/v3/smtp/email'
            headers = {'api-key': os.environ['BREVO_API_KEY']}
            payload = {'sender': {'email': sender, 'name': 'TrueWealth AI'}, 'to': [{'email': recipient}], 'subject': subject, 'textContent': text}
        else:
            url = 'https://api.resend.com/emails'
            headers = {'Authorization': 'Bearer ' + os.environ['RESEND_API_KEY']}
            payload = {'from': sender, 'to': [recipient], 'subject': subject, 'text': text}
        headers.update({'Content-Type': 'application/json', 'Accept': 'application/json'})
        request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method='POST')
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                if response.status not in (200, 201, 202):
                    raise RuntimeError('Email provider rejected delivery.')
        except urllib.error.HTTPError as error:
            try:
                detail = json.load(error)
            except (ValueError, TypeError):
                detail = {}
            message = str(detail.get('message', ''))
            address = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', message) if 'unrecognised IP' in message else None
            logger = logging.getLogger('backend')
            if address:
                logger.warning('Email delivery blocked by Brevo IP allowlist; authorize outbound IP %s.', address.group(0))
            else:
                code = re.sub(r'[^A-Za-z0-9_-]', '', str(detail.get('code', 'unknown')))[:64]
                logger.warning('Email provider rejected delivery: HTTP %s, code %s. Verify transactional account activation and sender.', error.code, code)
            raise RuntimeError('Email delivery failed. Check the sender verification and provider configuration.') from None
        except (urllib.error.URLError, TimeoutError):
            raise RuntimeError('Email delivery failed. Check the sender verification and provider configuration.') from None
        return
    message = EmailMessage()
    message['From'], message['To'], message['Subject'] = sender, recipient, subject
    message.set_content(text)
    with smtplib.SMTP(os.environ['SMTP_HOST'], int(os.getenv('SMTP_PORT', '587')), timeout=15) as server:
        if os.getenv('SMTP_STARTTLS', 'true').lower() == 'true':
            server.starttls(context=ssl.create_default_context())
        server.login(os.environ['SMTP_USERNAME'], os.environ['SMTP_PASSWORD'])
        server.send_message(message)
