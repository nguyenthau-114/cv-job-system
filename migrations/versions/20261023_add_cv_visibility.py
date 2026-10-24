"""Add CV visibility without changing existing CV data.

Revision ID: b73d8a4c9f10
Revises: a22f6b9d3e02

Downgrade removes visibility flags only; CV records and files are retained.
"""
from alembic import op
import sqlalchemy as sa


revision = "b73d8a4c9f10"
down_revision = "a22f6b9d3e02"
branch_labels = None
depends_on = None


def upgrade():
    # Mặc định 0 giữ CV cũ hiển thị và áp dụng cho cả bản ghi mới.
    op.add_column("cvs", sa.Column(
        "is_hidden", sa.Boolean(), nullable=False, server_default="0"
    ))


def downgrade():
    # Chỉ bỏ cờ ẩn; không xóa CV, file hoặc lịch sử ứng tuyển.
    op.drop_column("cvs", "is_hidden")
