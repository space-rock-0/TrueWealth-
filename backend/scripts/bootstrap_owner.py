"""Provision the explicitly authorized first account and request its verification email.

The generated password is saved only to the ignored local .deployment directory.
"""
import http.cookiejar
import json
import secrets
import urllib.error
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[2]
handoff = root / '.deployment' / 'owner-account.json'
handoff.parent.mkdir(exist_ok=True)
base = 'https://truewealth-sagi.vercel.app'
if handoff.exists():
    raise SystemExit('Owner handoff already exists. Use its account details rather than creating another account.')
credentials = {'site': base, 'username': 'sagi_siddhartha', 'email': 'sagi15sid05@gmail.com', 'password': secrets.token_urlsafe(32)}
with handoff.open('x', encoding='utf-8') as output:
    json.dump(credentials, output, indent=2)
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
with opener.open(base + '/api/auth/csrf', timeout=60) as response:
    response.read()
token = next(cookie.value for cookie in jar if cookie.name == 'tw_csrf')
payload = {k: credentials[k] for k in ('username', 'email', 'password')}
request = urllib.request.Request(base + '/api/auth/register', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', 'X-CSRF-Token': token, 'Origin': base}, method='POST')
try:
    with opener.open(request, timeout=60) as response:
        result = json.load(response)
    print(json.dumps({'status': 'verification_email_requested', 'username': credentials['username'], 'message': result.get('message'), 'handoff_file': str(handoff)}), flush=True)
except urllib.error.HTTPError as error:
    try:
        detail = json.load(error).get('detail')
    except ValueError:
        detail = 'Request failed.'
    print(json.dumps({'status': 'registration_failed', 'http_status': error.code, 'detail': detail, 'handoff_file': str(handoff)}), flush=True)
    raise SystemExit(1)
