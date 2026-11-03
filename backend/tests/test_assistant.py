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
    assistant._daily_requests.clear()
    assistant._last_started.clear()
    assistant._active_requests.clear()
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

def test_one_call_sends_question_static_knowledge_and_safe_screen_context(client, monkeypatch):
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
    result=client.post('/api/assistant/chat',json={'message':'O que é CDB?', 'context':'equities'},
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
    assert payload['messages'][0]['content'].endswith('Contexto não sensível da tela atual: Ações. Use essa informação somente se ajudar a responder.')
    assert payload['messages'][1]['content'] == 'O que é CDB?'
    assert provider_headers['User-Agent'] == 'InvestmentDashboard/1.2'
    assert provider_headers['Authorization'] == f'Bearer {groq_key}'
    sent = str(provider_call)
    assert supabase_token not in sent
    assert groq_key not in result.text
    assert 'operations' not in sent.lower() and 'saldo' not in sent.lower()

def test_screen_context_is_allowlisted(client):
    app.dependency_overrides[authenticate] = lambda: Principal(uuid4())
    assert client.post('/api/assistant/chat', json={'message': 'Explique este gráfico', 'context': 'private-portfolio'}).status_code == 422
    assert client.post('/api/assistant/chat', json={'message': 'Explique este gráfico', 'owner_id': str(uuid4())}).status_code == 422

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
    response = client.post('/api/assistant/chat',json={'message':'CDI?'})
    assert response.status_code == 429
    assert response.headers['Retry-After'] == '60'


def test_configurable_admin_and_private_limits(monkeypatch):
    admin_id, user_id = uuid4(), uuid4()
    monkeypatch.setattr(assistant.settings, 'invitation_admin_ids', [admin_id])
    monkeypatch.setattr(assistant.settings, 'assistant_admin_per_minute', 12)
    monkeypatch.setattr(assistant.settings, 'assistant_admin_per_day', 600)
    monkeypatch.setattr(assistant.settings, 'assistant_user_per_day', 120)
    assert assistant._limits(Principal(admin_id)) == (12, 600)
    assert assistant._limits(Principal(None)) == (12, 600)
    assert assistant._limits(Principal(user_id)) == (5, 120)


def test_limits_read_environment_and_reject_unbounded_values(monkeypatch):
    from pydantic import ValidationError
    monkeypatch.setenv('ASSISTANT_ADMIN_PER_DAY', '750')
    monkeypatch.setenv('ASSISTANT_USER_PER_DAY', '150')
    config = Settings(_env_file=None)
    assert config.assistant_admin_per_day == 750
    assert config.assistant_user_per_day == 150
    monkeypatch.setenv('ASSISTANT_ADMIN_PER_DAY', '0')
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_daily_limit_resets_at_utc_date_change(client, monkeypatch):
    from datetime import timedelta
    identity = Principal(uuid4())
    app.dependency_overrides[authenticate] = lambda: identity
    monkeypatch.setattr(assistant.settings, 'groq_api_key', type(assistant.settings.groq_api_key)('mock-key'))
    monkeypatch.setattr(assistant.settings, 'assistant_user_per_day', 1)
    key = str(identity.user_id)
    today = assistant.datetime.now(assistant.timezone.utc).date()
    assistant._daily_requests[key] = (today, 1)
    response = client.post('/api/assistant/chat', json={'message': 'CDI?'})
    assert response.status_code == 429 and 'diário' in response.json()['detail']
    assistant._daily_requests[key] = (today - timedelta(days=1), 1)
    from sqlalchemy.orm import Session
    from app.database import engine
    with Session(engine) as db:
        lease = assistant._reserve_request(identity, db)
        assert assistant._daily_requests[key] == (today, 1)
        assistant._release_request(identity, lease, db)


def test_inflight_and_cooldown_block_duplicate_provider_calls(client, monkeypatch):
    from sqlalchemy.orm import Session
    from app.database import engine
    identity = Principal(uuid4())
    monkeypatch.setattr(assistant.settings, 'assistant_cooldown_seconds', 3)
    now = [100.0]
    monkeypatch.setattr(assistant, 'monotonic', lambda: now[0])
    with Session(engine) as db:
        lease = assistant._reserve_request(identity, db)
        with pytest.raises(assistant.HTTPException) as busy:
            assistant._reserve_request(identity, db)
        assert busy.value.status_code == 429 and 'respondendo' in busy.value.detail
        assistant._release_request(identity, lease, db)
        with pytest.raises(assistant.HTTPException) as cooldown:
            assistant._reserve_request(identity, db)
        assert cooldown.value.status_code == 429 and cooldown.value.headers['Retry-After'] == '3'
        now[0] += 3
        second = assistant._reserve_request(identity, db)
        assert len(assistant._requests[str(identity.user_id)]) == 2
        assistant._release_request(identity, second, db)


def test_provider_quota_is_not_retried_and_releases_inflight(client, monkeypatch):
    identity = Principal(uuid4())
    app.dependency_overrides[authenticate] = lambda: identity
    monkeypatch.setattr(assistant.settings, 'groq_api_key', type(assistant.settings.groq_api_key)('mock-key'))
    calls = []
    class FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs):
            calls.append(kwargs)
            return httpx.Response(429, headers={'Retry-After': '120'})
    monkeypatch.setattr(assistant.httpx, 'AsyncClient', FakeClient)
    response = client.post('/api/assistant/chat', json={'message': 'CDI?'})
    assert response.status_code == 503
    assert response.headers['Retry-After'] == '120'
    assert len(calls) == 1
    assert str(identity.user_id) not in assistant._active_requests
    assert assistant._daily_requests[str(identity.user_id)][1] == 1


def test_postgresql_uses_shared_reservation_and_releases_same_lease(client):
    from types import SimpleNamespace
    identity = Principal(uuid4())
    class Database:
        bind = SimpleNamespace(dialect=SimpleNamespace(name='postgresql'))
        def __init__(self): self.calls = []; self.commits = 0
        def execute(self, statement, params): self.calls.append((str(statement), params))
        def scalar(self, statement, params): self.calls.append((str(statement), params)); return 'allowed'
        def commit(self): self.commits += 1
    db = Database()
    lease = assistant._reserve_request(identity, db)
    assistant._release_request(identity, lease, db)
    assert db.commits == 2
    reserve = next(params for statement, params in db.calls if 'reserve_dashboard' in statement)
    release = next(params for statement, params in db.calls if 'release_dashboard' in statement)
    assert reserve['request_id'] == release['request_id'] == lease
    assert reserve['per_minute'] == 5 and reserve['per_day'] == 100
