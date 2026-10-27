import os

# Nunca inicializar testes com configurações privadas do .env.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["MIGRATION_DATABASE_URL"] = ""
os.environ["API_TOKEN"] = "test-only-token-not-for-production"
os.environ["AUTH_MODE"] = "local"
os.environ["ENVIRONMENT"] = "test"
os.environ["SUPABASE_URL"] = ""
os.environ["ALLOWED_USER_IDS"] = "[]"
os.environ["CORS_ORIGIN"] = "http://localhost:5173"
