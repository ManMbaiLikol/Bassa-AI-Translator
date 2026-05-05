"""add_translation_history

Revision ID: a031264ffd36
Revises: b27f06b92144
Create Date: 2026-04-02 10:17:03.242885

Ajoute la table translation_history pour l'historique des traductions.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a031264ffd36'
down_revision: Union[str, Sequence[str], None] = 'b27f06b92144'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'translation_history',
        sa.Column('id',               sa.Integer(),    primary_key=True, autoincrement=True),
        sa.Column('user_id',          sa.Integer(),    sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('source_language',  sa.String(2),    nullable=False),
        sa.Column('source_text',      sa.Text(),       nullable=False),
        sa.Column('translated_text',  sa.Text(),       nullable=False),
        sa.Column('engine',           sa.String(50),   nullable=False),
        sa.Column('confidence',       sa.Float(),      nullable=True),
        sa.Column('created_at',       sa.DateTime(),   server_default=sa.text('NOW()')),
    )
    op.create_index('ix_translation_history_id',              'translation_history', ['id'],              unique=True)
    op.create_index('ix_translation_history_user_id',         'translation_history', ['user_id'])
    op.create_index('ix_translation_history_source_language', 'translation_history', ['source_language'])
    op.create_index('ix_translation_history_engine',          'translation_history', ['engine'])
    op.create_index('ix_translation_history_created_at',      'translation_history', ['created_at'])


def downgrade() -> None:
    op.drop_table('translation_history')
