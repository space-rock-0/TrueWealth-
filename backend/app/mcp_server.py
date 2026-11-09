"""MCP stdio bridge to the authenticated TrueWealth API; no extra service needed.

Launch: python -m app.mcp_server. Credentials live only in process environment.
"""
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


API = os.getenv('TRUEWEALTH_API_URL', 'http://127.0.0.1:5001').rstrip('/')
_parsed = urllib.parse.urlsplit(API)
if _parsed.scheme != 'https' and not (_parsed.scheme == 'http' and _parsed.hostname in ('localhost', '127.0.0.1')):
    raise RuntimeError('Use HTTPS for a remote TrueWealth API.')
cookies = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
authenticated = False


def request(method, path, body=None, ai=False):
    headers = {'Content-Type': 'application/json'}
    if method == 'POST':
        headers['X-CSRF-Token'] = next((c.value for c in cookies if c.name == 'tw_csrf'), '')
    if ai:
        provider = os.getenv('TRUEWEALTH_MCP_PROVIDER', 'groq')
        if provider not in ('groq', 'openai', 'anthropic', 'gemini'):
            raise ValueError('Unsupported provider.')
        headers['X-LLM-Provider'] = provider
        for env, header in [('TRUEWEALTH_MCP_MODEL', 'X-LLM-Model'), ('TRUEWEALTH_MCP_API_KEY', 'X-LLM-API-Key')]:
            if os.getenv(env):
                headers[header] = os.environ[env]
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
    try:
        with opener.open(req, timeout=180) as response:
            return json.loads(response.read(4 * 1024 * 1024))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'API returned HTTP {exc.code}; check account, provider settings, and document status.') from None


def authenticate():
    global authenticated
    if authenticated:
        return
    username, password = os.getenv('TRUEWEALTH_MCP_USERNAME'), os.getenv('TRUEWEALTH_MCP_PASSWORD')
    if not username or not password:
        raise RuntimeError('Configure TRUEWEALTH_MCP_USERNAME and TRUEWEALTH_MCP_PASSWORD for a verified account.')
    request('GET', '/api/auth/csrf')
    request('POST', '/api/auth/login', {'identifier': username, 'password': password})
    authenticated = True


def schema(properties=None, required=None):
    return {'type': 'object', 'properties': properties or {}, 'required': required or [], 'additionalProperties': False}


ID = {'type': 'integer', 'minimum': 1}
TOOLS = [
    {'name': 'list_statements', 'description': 'List bank statements owned by the signed-in account.', 'inputSchema': schema()},
    {'name': 'get_statement', 'description': 'Read extracted transactions and status for an owned statement.', 'inputSchema': schema({'statement_id': ID}, ['statement_id'])},
    {'name': 'analyze_statement', 'description': 'Extract transactions with the configured cloud AI provider. This may incur provider charges.', 'inputSchema': schema({'statement_id': ID}, ['statement_id'])},
    {'name': 'ask_statement', 'description': 'Ask a grounded question about an owned statement. This may incur provider charges.', 'inputSchema': schema({'statement_id': ID, 'question': {'type': 'string', 'minLength': 1, 'maxLength': 2000}}, ['statement_id', 'question'])},
    {'name': 'financial_summary', 'description': 'Get computed financial totals, separated by currency.', 'inputSchema': schema()},
]


def call(name, arguments):
    authenticate()
    if name == 'list_statements':
        return request('GET', '/api/statements')
    if name == 'financial_summary':
        return request('GET', '/api/statements/analytics/summary')
    if name not in ('get_statement', 'analyze_statement', 'ask_statement'):
        raise ValueError('Unknown tool.')
    statement_id = arguments.get('statement_id')
    if not isinstance(statement_id, int) or isinstance(statement_id, bool) or statement_id < 1:
        raise ValueError('A positive statement_id is required.')
    path = f'/api/statements/{statement_id}'
    if name == 'get_statement':
        return request('GET', path)
    if name == 'analyze_statement':
        return request('POST', path + '/analyze', {}, ai=True)
    return request('POST', path + '/question', {'question': arguments.get('question', '')}, ai=True)


def handle(message):
    method, ident = message.get('method'), message.get('id')
    if ident is None:
        return None
    if method == 'initialize':
        result = {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'truewealth', 'version': '1.0.0'}}
    elif method == 'ping':
        result = {}
    elif method == 'tools/list':
        result = {'tools': TOOLS}
    elif method == 'tools/call':
        params = message.get('params') or {}
        try:
            value = call(params.get('name'), params.get('arguments') or {})
            result = {'content': [{'type': 'text', 'text': json.dumps(value)}]}
        except Exception as exc:
            result = {'isError': True, 'content': [{'type': 'text', 'text': str(exc) if isinstance(exc, (RuntimeError, ValueError)) else 'Request failed.'}]}
    else:
        return {'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32601, 'message': 'Method not found.'}}
    return {'jsonrpc': '2.0', 'id': ident, 'result': result}


def main():
    for line in sys.stdin:
        try:
            response = handle(json.loads(line))
        except (ValueError, TypeError, AttributeError):
            response = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Invalid request.'}}
        if response is not None:
            print(json.dumps(response), flush=True)


if __name__ == '__main__':
    main()
