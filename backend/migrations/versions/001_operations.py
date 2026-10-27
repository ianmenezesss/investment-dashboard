"""Persistência inicial de operações."""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None


def upgrade():
    op.create_table("operations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("kind", sa.String(4), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("price", sa.Numeric(20, 8), nullable=False),
        sa.Column("fees", sa.Numeric(20, 8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("operations")
