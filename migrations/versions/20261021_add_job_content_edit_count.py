"""Add the one-time content edit counter to jobs.

Revision ID: c21e4d8f6a01
Revises: ba1c91ecc416
"""
from alembic import op
import sqlalchemy as sa


revision = "c21e4d8f6a01"
down_revision = "ba1c91ecc416"
branch_labels = None
depends_on = None


def upgrade():
    # Tin cũ nhận một lượt theo chính sách mới; giữ mặc định cho tin mới.
    op.add_column("jobs", sa.Column(
        "content_edit_count", sa.Integer(), nullable=False, server_default="0"
    ))


def downgrade():
    op.drop_column("jobs", "content_edit_count")
