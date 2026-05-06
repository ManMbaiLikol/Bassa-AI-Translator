"""add_grammatical_rules

Revision ID: 0002_add_grammatical_rules
Revises: 0001_create_full_schema
Create Date: 2026-05-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0002_add_grammatical_rules'
down_revision: Union[str, Sequence[str], None] = '0001_create_full_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'grammatical_rules',
        sa.Column('id',              sa.Integer(),   primary_key=True, autoincrement=True),
        sa.Column('rule_name',       sa.String(255), nullable=False),
        sa.Column('source_language', sa.String(2),   nullable=False),
        sa.Column('pattern',         sa.Text(),      nullable=False),
        sa.Column('transformation',  sa.Text(),      nullable=False),
        sa.Column('priority',        sa.Integer(),   nullable=True, server_default=sa.text('0')),
        sa.Column('is_active',       sa.Boolean(),   nullable=True, server_default=sa.text('1')),
        sa.Column('created_at',      sa.DateTime(),  server_default=sa.text('NOW()')),
    )
    op.create_index('ix_grammatical_rules_id', 'grammatical_rules', ['id'], unique=False)


def downgrade() -> None:
    op.drop_table('grammatical_rules')
