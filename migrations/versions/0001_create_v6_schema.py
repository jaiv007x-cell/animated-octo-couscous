"""create v6 production schema

Revision ID: 0001_create_v6_schema
Revises:
Create Date: 2026-06-27
"""
from __future__ import annotations
from alembic import op
from sqlmodel import SQLModel
import app.models  # noqa: F401

revision = "0001_create_v6_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.drop_all(bind=bind)
