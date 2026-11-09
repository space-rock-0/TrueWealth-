import io
import json
import urllib.error
from unittest.mock import MagicMock

import pytest
from app.core import email_delivery


@pytest.fixture
def brevo(monkeypatch):
    monkeypatch.setenv('EMAIL_PROVIDER', 'brevo')
    monkeypatch.setenv('EMAIL_FROM', 'sender@example.test')
    monkeypatch.setenv('BREVO_API_KEY', 'test-api-key-only')


def test_https_email_payload(brevo, monkeypatch):
    response = MagicMock()
    response.__enter__.return_value.status = 201
    opener = MagicMock(return_value=response)
    monkeypatch.setattr(email_delivery.urllib.request, 'urlopen', opener)
    email_delivery.send_email('recipient@example.test', 'Verify', 'One-time verification content')
    request = opener.call_args.args[0]
    assert request.full_url == 'https://api.brevo.com/v3/smtp/email'
    assert json.loads(request.data)['to'] == [{'email': 'recipient@example.test'}]
    assert email_delivery.email_configured()


def test_email_ip_failure_logs_safe_diagnostic(brevo, monkeypatch, caplog):
    error = urllib.error.HTTPError('https://api.brevo.com', 401, 'Unauthorized', {}, io.BytesIO(json.dumps({'message': 'We have detected you are using an unrecognised IP address 203.0.113.10', 'code': 'unauthorized'}).encode()))
    monkeypatch.setattr(email_delivery.urllib.request, 'urlopen', MagicMock(side_effect=error))
    with pytest.raises(RuntimeError):
        email_delivery.send_email('recipient@example.test', 'Verify', 'Secret verification token')
    assert '203.0.113.10' in caplog.text
    assert 'test-api-key-only' not in caplog.text
    assert 'Secret verification token' not in caplog.text


def test_sender_readiness_check_never_sends_email(brevo, monkeypatch, caplog):
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'{"senders":[{"email":"sender@example.test","active":true}]}'
    opener = MagicMock(return_value=response)
    monkeypatch.setattr(email_delivery.urllib.request, 'urlopen', opener)
    email_delivery.inspect_email_sender()
    assert opener.call_args.args[0].get_method() == 'GET'
    assert 'test-api-key-only' not in caplog.text
