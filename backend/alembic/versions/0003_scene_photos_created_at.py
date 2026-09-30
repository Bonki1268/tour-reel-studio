"""scene_photos.created_at：依上傳順序列出實景照（spec 0007）

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scene_photos",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("scene_photos", "created_at")
