"""Exercise real account-scoped document routes without calling a paid provider."""
import base64
import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine

from app import statements
from app.auth import get_current_user, require_csrf
from app.core.db import AppUser
from app.core.rate_limit import limiter


@pytest.fixture
def api(tmp_path, monkeypatch):
    engine = create_engine(f'sqlite:///{tmp_path / "statements.sqlite"}', connect_args={'check_same_thread': False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(statements, 'engine', engine)
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(statements.router)
    app.dependency_overrides[get_current_user] = lambda: AppUser(id=11, email='one@example.com', username='one', password_hash='unused')
    app.dependency_overrides[require_csrf] = lambda: None
    with TestClient(app) as client:
        yield client, app
    engine.dispose()


def upload(client):
    return client.post('/api/statements', json={'filename': 'statement.txt', 'content': base64.b64encode(b'Account number: 123456789012\n2026-01-01 salary credit 1000.00 USD\n').decode()})


def test_document_ownership_and_duplicate_detection(api):
    client, app = api
    response = upload(client)
    assert response.status_code == 201
    statement_id = response.json()['id']
    assert upload(client).json()['id'] == statement_id
    assert len(client.get('/api/statements').json()) == 1
    app.dependency_overrides[get_current_user] = lambda: AppUser(id=22, email='two@example.com', username='two', password_hash='unused')
    assert client.get('/api/statements').json() == []
    assert client.get(f'/api/statements/{statement_id}').status_code == 404
    assert client.get(f'/api/statements/{statement_id}/export').status_code == 404
    assert client.post(f'/api/statements/{statement_id}/delete').status_code == 404


def test_extraction_validation_and_csv_formula_protection(api, monkeypatch):
    client, _ = api
    statement_id = upload(client).json()['id']
    async def generate(prompt, config, **kwargs):
        return json.dumps([{'date': '2026-01-01', 'description': '=MALICIOUS()', 'credit': '1000.00', 'debit': '0.00', 'currency': 'USD'}])
    monkeypatch.setattr(statements, 'generate', generate)
    response = client.post(f'/api/statements/{statement_id}/analyze')
    assert response.status_code == 200, response.text
    assert response.json()['transaction_count'] == 1
    summary = client.get('/api/statements/analytics/summary?year=2026&quarter=1').json()
    assert float(summary['currencies']['USD']['credits']) == 1000
    assert client.get('/api/statements/analytics/summary?year=2026&quarter=2').json()['currencies'] == {}
    assert client.get(f'/api/statements/{statement_id}/report').status_code == 200
    assert "'=MALICIOUS()" in client.get(f'/api/statements/{statement_id}/export').text
    async def invalid(prompt, config, **kwargs):
        return '[{"date":"not-a-date","credit":-20}]'
    monkeypatch.setattr(statements, 'generate', invalid)
    assert client.post(f'/api/statements/{statement_id}/analyze').status_code == 422
    assert client.get(f'/api/statements/{statement_id}').json()['status'] == 'failed'


def test_upload_validation_and_pii_redaction(api):
    client, _ = api
    assert client.post('/api/statements', json={'filename': 'bad.pdf', 'content': '!!!'}).status_code == 400
    assert '123456789012' not in statements.redact('Account number: 123456789012')
    assert 'user@example.com' not in statements.redact('email user@example.com')


def test_background_analysis_and_mcp_handshake(api, monkeypatch):
    client, _ = api
    statement_id = upload(client).json()['id']
    async def generate(prompt, config, **kwargs):
        return '[{"date":"2026-01-01","description":"Salary","credit":1000,"currency":"USD"}]'
    monkeypatch.setattr(statements, 'generate', generate)
    response = client.post(f'/api/statements/{statement_id}/analyze-background')
    assert response.status_code == 202
    assert client.get(f'/api/statements/{statement_id}').json()['status'] == 'completed'
    from app.mcp_server import handle
    assert handle({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'})['result']['capabilities']['tools'] == {}
    assert len(handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})['result']['tools']) == 5


def test_provider_json_wrapper_null_columns_and_amount_formatting():
    content = '```json\n{"transactions":[{"date":"09 Nov 2026","description":"Salary","credit":"1,00,000.00","debit":null,"balance":"₹ 1,20,000.00","currency":"inr"}]}\n```'
    rows = statements.parse_transactions(content)
    assert rows[0]['date'] == '2026-11-09'
    assert rows[0]['credit'] == '100000.00'
    assert rows[0]['debit'] == '0'
    assert rows[0]['balance'] == '120000.00'
    assert rows[0]['currency'] == 'INR'


def test_currency_requires_evidence_and_errors_omit_private_values():
    content = '[{"date":"2026-11-09","description":"Private merchant","deposit":"1,000.00","withdrawal":"-"}]'
    rows = statements.parse_transactions(content, 'Account currency: INR')
    assert rows[0]['currency'] == 'INR'
    with pytest.raises(Exception) as missing:
        statements.parse_transactions(content)
    assert 'currency' in missing.value.detail
    assert 'Private merchant' not in missing.value.detail
    with pytest.raises(Exception) as malformed:
        statements.parse_transactions('{"transactions": [')
    assert 'JSON' in malformed.value.detail


def test_structured_extraction_sets_budget_and_rejects_truncated_results(monkeypatch):
    options_seen = {}
    class TruncatedGateway:
        def __init__(self, tier):
            pass
        def invoke(self, prompt, generation_options=None):
            options_seen.update(generation_options)
            from app.tools.model_gateway import GatewayMessage
            return GatewayMessage('{"transactions":[', 'test', False, None, 100, finish_reason='length')
    monkeypatch.setattr(statements, 'Gateway', TruncatedGateway)
    config = {'provider': 'groq', 'model': 'openai/gpt-oss-120b', 'api_key': 'test-only-key'}
    with pytest.raises(Exception) as truncated:
        asyncio.run(statements.generate('Return JSON', config, structured=True))
    assert 'output limit' in truncated.value.detail
    assert options_seen['max_tokens'] == 16384
    assert options_seen['response_format'] == {'type': 'json_object'}
    from app.tools.model_gateway import _request_model_config
    assert _request_model_config.get() is None
