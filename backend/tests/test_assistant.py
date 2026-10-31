from collections import defaultdict, deque
from unittest.mock import patch
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from app import assistant
from app.main import app
from app.auth import authenticate, Principal
from app.database import Settings

@pytest.fixture
def client():
    assistant._requests.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(authenticate, None)

def test_auth_required(client):
    response = client.post('/api/assistant/chat', json={'message':'O que é CDB?'})
    assert response.status_code == 401

def test_key_missing(client, monkeypatch):
    app.dependency_overrides[authenticate] = lambda: Principal(uuid4())
    monkeypatch.setattr(assistant.settings, 'groq_api_key', type(assistant.settings.groq_api_key)(''))
    assert client.post('/api/assistant/chat', json={'message':'O que é CDB?'}).status_code == 503

def test_groq_settings_read_environment_only(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'sqlite://')
    monkeypatch.setenv('API_TOKEN', 'local-test-token')
    monkeypatch.setenv('GROQ_API_KEY', 'environment-test-key')
    monkeypatch.setenv('GROQ_MODEL', 'qwen/test-override')
    config = Settings(_env_file=None)
    assert config.groq_api_key.get_secret_value() == 'environment-test-key'
    assert config.groq_model == 'qwen/test-override'
    assert 'environment-test-key' not in repr(config.groq_api_key)

@pytest.mark.parametrize('message', ['', 'x' * 1001])
def test_message_validation(client, message):
    app.dependency_overrides[authenticate] = lambda: Principal(uuid4())
    assert client.post('/api/assistant/chat', json={'message':message}).status_code == 422

def test_one_call_no_private_context(client, monkeypatch):
    app.dependency_overrides[authenticate] = lambda: Principal(uuid4())
    groq_key = 'mock-groq-api-key'
    supabase_token = 'mock-supabase-session-token'
    monkeypatch.setattr(assistant.settings, 'groq_api_key', type(assistant.settings.groq_api_key)(groq_key))
    monkeypatch.setattr(assistant.settings, 'groq_model', 'qwen/qwen3.8-27b')
    calls = []
    class Response:
        status_code=200
        def raise_for_status(self): pass
        def json(self): return {'choices':[{'message':{'content':'CDB é renda fixa.'}}]}
    class FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def post(self,*args,**kwargs): calls.append(kwargs); return Response()
    monkeypatch.setattr(assistant.httpx,'AsyncClient',FakeClient)
    result=client.post('/api/assistant/chat',json={'message':'O que é CDB?'},
                       headers={'Authorization': f'Bearer {supabase_token}'})
    assert result.status_code == 200 and result.json()['answer']
    assert len(calls) == 1
    provider_call = calls[0]
    payload = provider_call['json']
    provider_headers = provider_call['headers']
    assert payload['model'] == 'qwen/qwen3.8-27b'
    assert payload['max_completion_tokens'] == 350
    assert 'max_tokens' not in payload
    assert len(payload['messages']) == 2
    assert provider_headers['User-Agent'] == 'InvestmentDashboard/1.2'
    assert provider_headers['Authorization'] == f'Bearer {groq_key}'
    sent = str(provider_call)
    assert supabase_token not in sent
    assert groq_key not in result.text
    assert 'operations' not in sent.lower() and 'saldo' not in sent.lower()

@pytest.mark.parametrize('failure,status', [('429',503),('timeout',503),('connection',503)])
def test_provider_failures(client, monkeypatch, failure, status):
    app.dependency_overrides[authenticate] = lambda: Principal(uuid4())
    monkeypatch.setattr(assistant.settings,'groq_api_key',type(assistant.settings.groq_api_key)('mock-key'))
    class Response:
        status_code=429 if failure=='429' else 500
        def raise_for_status(self):
            if self.status_code!=200: raise httpx.HTTPStatusError('upstream',request=httpx.Request('POST','https://unit.test'),response=httpx.Response(self.status_code))
    class FakeClient:
        def __init__(self,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def post(self,*args,**kwargs):
            if failure=='timeout': raise httpx.TimeoutException('timeout')
            if failure=='connection': raise httpx.ConnectError('offline')
            return Response()
    monkeypatch.setattr(assistant.httpx,'AsyncClient',FakeClient)
    assert client.post('/api/assistant/chat',json={'message':'CDI?'}).status_code==status

def test_per_user_limit(client, monkeypatch):
    app.dependency_overrides[authenticate] = lambda: Principal(uuid4())
    monkeypatch.setattr(assistant.settings,'groq_api_key',type(assistant.settings.groq_api_key)('mock-key'))
    identity=assistant.Principal(uuid4())
    app.dependency_overrides[authenticate]=lambda: identity
    assistant._requests[str(identity.user_id)]=deque([assistant.monotonic()]*5)
    assert client.post('/api/assistant/chat',json={'message':'CDI?'}).status_code==429
