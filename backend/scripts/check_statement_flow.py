"""Verify the local live session/document flow without provider charges."""
import base64
import http.cookiejar
import json
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.auth import VERIFY_EMAIL, PRODUCTION
from app.core.db import AppUser, AuthSession, AuthToken, engine
from app.statements import Statement
from sqlalchemy import delete
from sqlmodel import Session

if PRODUCTION or VERIFY_EMAIL:
    raise SystemExit('This temporary-account check is restricted to local development without email verification.')

BASE = 'http://127.0.0.1:5001'
users = []


def client():
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    def send(method, path, data=None):
        headers = {'Content-Type': 'application/json'}
        if method == 'POST':
            headers['X-CSRF-Token'] = next((c.value for c in jar if c.name == 'tw_csrf'), '')
        req = urllib.request.Request(BASE + path, data=json.dumps(data).encode() if data is not None else None, headers=headers, method=method)
        with opener.open(req, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    return send


def account():
    send = client()
    send('GET', '/api/auth/csrf')
    name = 'check_' + secrets.token_hex(5)
    result = send('POST', '/api/auth/register', {'username': name, 'email': name + '@example.test', 'password': secrets.token_urlsafe(24)})
    users.append(result['id'])
    assert send('GET', '/api/auth/me')['id'] == result['id']
    return send


try:
    first = account()
    document = first('POST', '/api/statements', {'filename': 'generated-check.txt', 'content': base64.b64encode(b'2026-01-01 Salary credit USD 1000.00\nGenerated integration check statement only.').decode()})
    document_id = document['id']
    assert first('GET', f'/api/statements/{document_id}')['id'] == document_id
    assert any(x['id'] == document_id for x in first('GET', '/api/statements'))
    second = account()
    assert second('GET', '/api/statements') == []
    try:
        second('GET', f'/api/statements/{document_id}')
        raise AssertionError('Document ownership boundary failed')
    except urllib.error.HTTPError as exc:
        assert exc.code == 404
    first('POST', f'/api/statements/{document_id}/delete', {})
    first('POST', '/api/auth/logout', {})
    try:
        first('GET', '/api/statements')
        raise AssertionError('Sign-out did not revoke access')
    except urllib.error.HTTPError as exc:
        assert exc.code == 401
    print('Live account/session/upload/history/ownership/delete/logout flow: passed. No paid AI calls.')
finally:
    with Session(engine) as db:
        for user_id in users:
            for model in (Statement, AuthToken, AuthSession):
                db.exec(delete(model).where(model.user_id == user_id))
            user = db.get(AppUser, user_id)
            if user:
                db.delete(user)
        db.commit()
