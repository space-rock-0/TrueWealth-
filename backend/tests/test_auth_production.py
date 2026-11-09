import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from app import auth
from app.core.db import AuthToken
from app.core.rate_limit import limiter


@pytest.fixture
def account_api(tmp_path, monkeypatch):
    engine = create_engine(f'sqlite:///{tmp_path / "accounts.sqlite"}', connect_args={'check_same_thread': False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(auth, 'engine', engine)
    monkeypatch.setattr(auth, 'VERIFY_EMAIL', False)
    app = FastAPI(); app.state.limiter = limiter; app.include_router(auth.router)
    with TestClient(app) as client:
        yield client, engine
    engine.dispose()


def csrf(client):
    client.get('/api/auth/csrf')
    client.headers['X-CSRF-Token'] = client.cookies['tw_csrf']


def register(client):
    csrf(client)
    response = client.post('/api/auth/register', json={'email': 'person@example.test', 'username': 'person', 'password': 'A-long-test-password!123'})
    assert response.status_code == 201, response.text
    client.headers['X-CSRF-Token'] = client.cookies['tw_csrf']
    return response


def test_account_cookie_csrf_login_and_logout(account_api):
    client, _ = account_api
    assert client.get('/api/auth/me').status_code == 401
    assert client.post('/api/auth/login', json={'identifier': 'person', 'password': 'wrong'}).status_code == 403
    response = register(client)
    assert 'HttpOnly' in response.headers['set-cookie']
    assert client.get('/api/auth/me').json()['username'] == 'person'
    assert client.post('/api/auth/logout').status_code == 204
    assert client.get('/api/auth/me').status_code == 401
    csrf(client)
    for identifier in ('person', 'person@example.test'):
        response = client.post('/api/auth/login', json={'identifier': identifier, 'password': 'A-long-test-password!123'})
        assert response.status_code == 200
        client.headers['X-CSRF-Token'] = client.cookies['tw_csrf']


def test_reset_is_one_time_and_revokes_sessions(account_api):
    client, engine = account_api
    user_id = register(client).json()['id']
    token = 'one-time-reset-token-for-testing-only'
    with Session(engine) as db:
        db.add(AuthToken(user_id=user_id, purpose='reset', token_digest=hashlib.sha256(token.encode()).hexdigest(), expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        db.commit()
    response = client.post('/api/auth/reset-password', json={'token': token, 'password': 'A-new-test-password!456'})
    assert response.status_code == 200
    assert client.get('/api/auth/me').status_code == 401
    with pytest.raises(HTTPException) as replay:
        auth._consume_token(token, 'reset')
    assert replay.value.status_code == 400


def test_registration_stays_closed_without_production_email(account_api, monkeypatch):
    client, _ = account_api
    monkeypatch.setattr(auth, 'VERIFY_EMAIL', True)
    monkeypatch.setattr(auth, 'email_configured', lambda: False)
    csrf(client)
    response = client.post('/api/auth/register', json={'email': 'person@example.test', 'username': 'person', 'password': 'A-long-test-password!123'})
    assert response.status_code == 503
