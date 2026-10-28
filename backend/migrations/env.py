from alembic import context
from app.database import engine, Base, settings
from sqlalchemy import create_engine, text
from app import models
from app.fixed_income import models as fixed_income_models
from app.fixed_income import observations

migration_engine = create_engine(settings.migration_database_url.get_secret_value(), hide_parameters=True, connect_args={"connect_timeout": 5}) if settings.migration_database_url.get_secret_value() else engine
with migration_engine.connect() as connection:
    if connection.dialect.name == "postgresql":
        connection.execute(text("SET lock_timeout = '5s'"))
        connection.execute(text("SET statement_timeout = '30s'"))
        connection.commit()
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
