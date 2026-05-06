"""create_full_schema

Revision ID: 0001_create_full_schema
Revises:
Create Date: 2026-05-06

Schema complet depuis zéro — remplace les 3 migrations précédentes.
Conçu pour fonctionner sur une base vide (Railway, CI, nouveau dev).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0001_create_full_schema'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id',              sa.Integer(),     primary_key=True, autoincrement=True),
        sa.Column('username',        sa.String(100),   nullable=False),
        sa.Column('email',           sa.String(191),   nullable=False),
        sa.Column('hashed_password', sa.String(255),   nullable=True),
        sa.Column('google_id',       sa.String(128),   nullable=True),
        sa.Column('role',            sa.Enum('contributor', 'reviewer', 'admin', name='userrole'),
                                     nullable=False, server_default='contributor'),
        sa.Column('created_at',      sa.DateTime(),    server_default=sa.text('NOW()')),
    )
    op.create_index('ix_users_id',        'users', ['id'],        unique=False)
    op.create_index('ix_users_username',  'users', ['username'],  unique=True)
    op.create_index('ix_users_email',     'users', ['email'],     unique=True)
    op.create_index('ix_users_google_id', 'users', ['google_id'], unique=True)

    op.create_table(
        'dictionary_entries',
        sa.Column('id',              sa.Integer(),     primary_key=True, autoincrement=True),
        sa.Column('source_language', sa.String(2),     nullable=False),
        sa.Column('source_word',     sa.String(191),   nullable=False),
        sa.Column('bassa_word',      sa.String(255),   nullable=False),
        sa.Column('phonetic',        sa.String(255),   nullable=True),
        sa.Column('category',        sa.String(50),    nullable=True),
        sa.Column('gender',          sa.String(20),    nullable=True),
        sa.Column('plural_form',     sa.String(255),   nullable=True),
        sa.Column('notes',           sa.Text(),        nullable=True),
        sa.Column('is_verified',     sa.Boolean(),     nullable=True, server_default=sa.text('0')),
        sa.Column('created_at',      sa.DateTime(),    server_default=sa.text('NOW()')),
        sa.Column('updated_at',      sa.DateTime(),    server_default=sa.text('NOW()')),
    )
    op.create_index('ix_dictionary_entries_id',              'dictionary_entries', ['id'],              unique=False)
    op.create_index('ix_dictionary_entries_source_language', 'dictionary_entries', ['source_language'], unique=False)
    op.create_index('ix_dictionary_entries_source_word',     'dictionary_entries', ['source_word'],     unique=False)

    op.create_table(
        'dictionary_examples',
        sa.Column('id',              sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('entry_id',        sa.Integer(), sa.ForeignKey('dictionary_entries.id', ondelete='CASCADE'), nullable=False),
        sa.Column('source_sentence', sa.Text(),    nullable=False),
        sa.Column('bassa_sentence',  sa.Text(),    nullable=False),
    )
    op.create_index('ix_dictionary_examples_id', 'dictionary_examples', ['id'], unique=False)

    op.create_table(
        'corpus_pairs',
        sa.Column('id',               sa.Integer(),    primary_key=True, autoincrement=True),
        sa.Column('source_language',  sa.String(2),    nullable=False),
        sa.Column('source_text',      sa.Text(),       nullable=False),
        sa.Column('bassa_text',       sa.Text(),       nullable=False),
        sa.Column('domain',           sa.String(100),  nullable=True),
        sa.Column('source_reference', sa.String(255),  nullable=True),
        sa.Column('is_verified',      sa.Boolean(),    nullable=True, server_default=sa.text('0')),
        sa.Column('created_at',       sa.DateTime(),   server_default=sa.text('NOW()')),
    )
    op.create_index('ix_corpus_pairs_id',              'corpus_pairs', ['id'],              unique=False)
    op.create_index('ix_corpus_pairs_source_language', 'corpus_pairs', ['source_language'], unique=False)

    op.create_table(
        'contributions',
        sa.Column('id',               sa.Integer(),  primary_key=True, autoincrement=True),
        sa.Column('contributor_id',   sa.Integer(),  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('type',             sa.Enum('dictionary', 'corpus', name='contributiontype'), nullable=False),
        sa.Column('status',           sa.Enum('submitted', 'under_review', 'approved', 'rejected', name='contributionstatus'),
                                       nullable=False, server_default='submitted'),
        sa.Column('source_language',  sa.String(2),  nullable=False),
        sa.Column('source_text',      sa.Text(),     nullable=False),
        sa.Column('bassa_text',       sa.Text(),     nullable=False),
        sa.Column('category',         sa.String(50), nullable=True),
        sa.Column('notes',            sa.Text(),     nullable=True),
        sa.Column('reviewer_id',      sa.Integer(),  sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reviewer_comment', sa.Text(),     nullable=True),
        sa.Column('created_at',       sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('reviewed_at',      sa.DateTime(), nullable=True),
    )
    op.create_index('ix_contributions_id', 'contributions', ['id'], unique=False)

    op.create_table(
        'translation_history',
        sa.Column('id',              sa.Integer(),   primary_key=True, autoincrement=True),
        sa.Column('user_id',         sa.Integer(),   sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('source_language', sa.String(2),   nullable=False),
        sa.Column('source_text',     sa.Text(),      nullable=False),
        sa.Column('translated_text', sa.Text(),      nullable=False),
        sa.Column('engine',          sa.String(50),  nullable=False),
        sa.Column('confidence',      sa.Float(),     nullable=True),
        sa.Column('created_at',      sa.DateTime(),  server_default=sa.text('NOW()')),
    )
    op.create_index('ix_translation_history_id',              'translation_history', ['id'],              unique=False)
    op.create_index('ix_translation_history_user_id',         'translation_history', ['user_id'],         unique=False)
    op.create_index('ix_translation_history_source_language', 'translation_history', ['source_language'], unique=False)
    op.create_index('ix_translation_history_engine',          'translation_history', ['engine'],          unique=False)
    op.create_index('ix_translation_history_created_at',      'translation_history', ['created_at'],      unique=False)

    op.create_table(
        'grammatical_rules',
        sa.Column('id',              sa.Integer(),    primary_key=True, autoincrement=True),
        sa.Column('rule_name',       sa.String(255),  nullable=False),
        sa.Column('source_language', sa.String(2),    nullable=False),
        sa.Column('pattern',         sa.Text(),       nullable=False),
        sa.Column('transformation',  sa.Text(),       nullable=False),
        sa.Column('priority',        sa.Integer(),    nullable=True, server_default=sa.text('0')),
        sa.Column('is_active',       sa.Boolean(),    nullable=True, server_default=sa.text('1')),
        sa.Column('created_at',      sa.DateTime(),   server_default=sa.text('NOW()')),
    )
    op.create_index('ix_grammatical_rules_id', 'grammatical_rules', ['id'], unique=False)


def downgrade() -> None:
    op.drop_table('grammatical_rules')
    op.drop_table('translation_history')
    op.drop_table('contributions')
    op.drop_table('corpus_pairs')
    op.drop_table('dictionary_examples')
    op.drop_table('dictionary_entries')
    op.drop_table('users')
