"""Transactional email over HTTPS for hosts that block SMTP egress."""
import json
import os
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage


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
