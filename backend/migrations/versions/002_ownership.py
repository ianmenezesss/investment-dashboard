"""Proprietário opcional para registros locais e RLS por identidade da API.

Não atribui, altera ou remove registros financeiros existentes.
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"


def upgrade():
    op.add_column("operations", sa.Column("owner_id", sa.Uuid(), nullable=True))
    op.create_index("ix_operations_owner_id", "operations", ["owner_id"])
    op.execute("ALTER TABLE operations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE operations FORCE ROW LEVEL SECURITY")
    rule = """(
      owner_id = NULLIF(current_setting('app.user_id', true), '')::uuid
      OR (owner_id IS NULL AND current_setting('app.auth_mode', true) = 'local')
    )"""
    op.execute(f"CREATE POLICY api_owner ON operations FOR ALL USING ({rule}) WITH CHECK ({rule})")


def downgrade():
    # Reverter ownership seria destrutivo; exigir intervenção explícita.
    raise RuntimeError("Downgrade de ownership bloqueado; preserve os dados e revise uma migração corretiva")
