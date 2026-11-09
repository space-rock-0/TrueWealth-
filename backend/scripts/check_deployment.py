"""Public HTTP deployment checks; no secrets or user records are printed."""
import json
import urllib.error
import urllib.request

targets = [
    ('https://truewealth-sagi.vercel.app/', 200, False),
    ('https://truewealth-api-sagi.onrender.com/api/health', 200, True),
    ('https://truewealth-sagi.vercel.app/api/health', 200, True),
    ('https://truewealth-sagi.vercel.app/api/auth/csrf', 200, True),
    ('https://truewealth-sagi.vercel.app/api/history', 401, True),
]
results = []
for url, expected, expects_json in targets:
    try:
        response = urllib.request.urlopen(url, timeout=60)
    except urllib.error.HTTPError as error:
        response = error
    except Exception as error:
        results.append({'url': url, 'passed': False, 'error': type(error).__name__})
        continue
    with response:
        raw = response.read()
        is_json = response.headers.get('Content-Type', '').startswith('application/json')
        passed = response.status == expected and (not expects_json or is_json)
        results.append({'url': url, 'status': response.status, 'passed': passed})
print(json.dumps(results), flush=True)
raise SystemExit(0 if all(row['passed'] for row in results) else 1)
