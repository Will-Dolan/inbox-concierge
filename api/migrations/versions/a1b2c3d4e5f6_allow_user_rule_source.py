"""allow 'user' as a rules.source (manual rule edits)

Revision ID: a1b2c3d4e5f6
Revises: c7af282e1fd7
Create Date: 2026-07-13 05:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'c7af282e1fd7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('ck_rules_source', 'rules', type_='check')
    op.create_check_constraint('ck_rules_source', 'rules', "source IN ('hand', 'agent', 'user')")


def downgrade() -> None:
    op.drop_constraint('ck_rules_source', 'rules', type_='check')
    op.create_check_constraint('ck_rules_source', 'rules', "source IN ('hand', 'agent')")
