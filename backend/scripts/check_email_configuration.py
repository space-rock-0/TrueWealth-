"""Check a Brevo sender without printing or persisting the API key."""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / '.env')

config = {'api_key': os.environ['BREVO_API_KEY'], 'sender': os.getenv('EMAIL_FROM', 'sagi15sid05@gmail.com')}
request = urllib.request.Request('https://api.brevo.com/v3/senders', headers={'api-key': config['api_key'], 'Accept': 'application/json'})
try:
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
    sender = next((item for item in payload.get('senders', []) if item.get('email', '').lower() == config['sender'].lower()), None)
    print(json.dumps({'api_authenticated': True, 'sender_registered': sender is not None, 'sender_active': bool(sender and sender.get('active'))}), flush=True)
except urllib.error.HTTPError as error:
    try:
        detail = json.load(error)
    except (ValueError, TypeError):
        detail = {}
    message = str(detail.get('message', '')).replace(config['api_key'], '[REDACTED]')[:600]
    print(json.dumps({'api_authenticated': False, 'http_status': error.code, 'code': detail.get('code'), 'message': message}), flush=True)
