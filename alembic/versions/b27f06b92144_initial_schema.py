"""initial_schema

Revision ID: b27f06b92144
Revises:
Create Date: 2026-04-01 23:26:16.482549

Changements par rapport à la base existante :
  - Supprime la table 'grammatical_rules' (obsolète, remplacée par rule_transform.py)
  - Ajoute les FK manquantes sur contributions et dictionary_examples
  - Réduit users.email de VARCHAR(255) à VARCHAR(191) (limite InnoDB utf8mb4)
  - Ajoute l'index unique ix_users_email
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = 'b27f06b92144'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Supprimer la table grammatical_rules (obsolète)
    op.drop_index('ix_grammatical_rules_id', table_name='grammatical_rules')
    op.drop_table('grammatical_rules')

    # Ajouter les foreign keys manquantes sur contributions
    op.create_foreign_key(
        'fk_contributions_contributor_id',
        'contributions', 'users',
        ['contributor_id'], ['id'],
    )
    op.create_foreign_key(
        'fk_contributions_reviewer_id',
        'contributions', 'users',
        ['reviewer_id'], ['id'],
    )

    # Ajouter la foreign key sur dictionary_examples
    op.create_foreign_key(
        'fk_dictionary_examples_entry_id',
        'dictionary_examples', 'dictionary_entries',
        ['entry_id'], ['id'],
        ondelete='CASCADE',
    )

    # Réduire users.email à 191 car VARCHAR > 191 cause des erreurs d'index
    # avec le charset utf8mb4 (InnoDB : 767 bytes max = 191 × 4 bytes)
    op.alter_column(
        'users', 'email',
        existing_type=mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=255),
        type_=sa.String(length=191),
        existing_nullable=False,
    )

    # Créer l'index unique ix_users_email
    op.create_index('ix_users_email', 'users', ['email'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_users_email', table_name='users')
    op.alter_column(
        'users', 'email',
        existing_type=sa.String(length=191),
        type_=mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=255),
        existing_nullable=False,
    )

    op.drop_constraint('fk_dictionary_examples_entry_id', 'dictionary_examples', type_='foreignkey')
    op.drop_constraint('fk_contributions_reviewer_id', 'contributions', type_='foreignkey')
    op.drop_constraint('fk_contributions_contributor_id', 'contributions', type_='foreignkey')

    op.create_table(
        'grammatical_rules',
        sa.Column('id', mysql.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('rule_name', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=255), nullable=False),
        sa.Column('source_language', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=2), nullable=False),
        sa.Column('pattern', mysql.TEXT(collation='utf8mb4_unicode_ci'), nullable=False),
        sa.Column('transformation', mysql.TEXT(collation='utf8mb4_unicode_ci'), nullable=False),
        sa.Column('priority', mysql.INTEGER(), autoincrement=False, nullable=True),
        sa.Column('is_active', mysql.TINYINT(display_width=1), autoincrement=False, nullable=True),
        sa.Column('created_at', mysql.DATETIME(), server_default=sa.text('(now())'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        mysql_collate='utf8mb4_unicode_ci',
        mysql_default_charset='utf8mb4',
        mysql_engine='InnoDB',
    )
    op.create_index('ix_grammatical_rules_id', 'grammatical_rules', ['id'], unique=False)
