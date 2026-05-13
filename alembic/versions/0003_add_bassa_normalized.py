"""add_bassa_word_normalized

Ajoute une colonne `bassa_word_normalized` (sans marques tonales) sur
`dictionary_entries` pour permettre la recherche tolérante aux accents.

La colonne est peuplée par `scripts/populate_normalized.py` après la migration.

Revision ID: 0003_add_bassa_normalized
Revises: 0002_add_grammatical_rules
Create Date: 2026-05-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0003_add_bassa_normalized'
down_revision: Union[str, Sequence[str], None] = '0002_add_grammatical_rules'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'dictionary_entries',
        sa.Column('bassa_word_normalized', sa.String(255), nullable=True),
    )
    op.create_index(
        'ix_dictionary_entries_bassa_word_normalized',
        'dictionary_entries',
        ['bassa_word_normalized'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_dictionary_entries_bassa_word_normalized', table_name='dictionary_entries')
    op.drop_column('dictionary_entries', 'bassa_word_normalized')
