import os
from unittest.mock import patch

# Pydantic also parses lower-priority dotenv sources even when env overrides exist.
# Isolate tests from private/malformed local files without changing application Settings.
_dotenv_patch = patch("pydantic_settings.sources.DotEnvSettingsSource.__call__", return_value={})
_dotenv_patch.start()


def pytest_unconfigure(config):
    _dotenv_patch.stop()

# Nunca inicializar testes com configurações privadas do .env.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["MIGRATION_DATABASE_URL"] = ""
os.environ["API_TOKEN"] = "test-only-token-not-for-production"
os.environ["AUTH_MODE"] = "local"
os.environ["ENVIRONMENT"] = "test"
os.environ["SUPABASE_URL"] = ""
os.environ["ALLOWED_USER_IDS"] = "[]"
os.environ["CORS_ORIGIN"] = "http://localhost:5173"
os.environ["MARKET_DATA_ENABLED"] = "false"
os.environ["INDIVIDUAL_EQUITY_HISTORY_ENABLED"] = "false"
os.environ["BRAPI_TOKEN"] = ""
