"""add body_html to messages_lite

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-13 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages_lite", sa.Column("body_html", sa.Text(), nullable=True))
    # Force a re-fetch for messages already cached under the old text-only
    # extraction so they pick up the sanitized HTML rendering too.
    op.execute("UPDATE messages_lite SET body_fetched = false WHERE body_fetched = true")


def downgrade() -> None:
    op.drop_column("messages_lite", "body_html")
