"""initial schema

Revision ID: 20260928_0001
Revises:
Create Date: 2026-09-28
"""
from typing import Sequence, Union

from alembic import op

from app.db import Base
from app import models  # noqa: F401

revision: str = "20260928_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind, checkfirst=True)
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            index.create(bind, checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind(), checkfirst=True)
