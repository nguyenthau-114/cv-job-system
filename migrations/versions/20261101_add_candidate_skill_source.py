"""Bổ sung nguồn kỹ năng CV còn thiếu trong lịch sử migration.

Revision ID: e95f3a7b8c41
Revises: d84e2f6a7b30

Chỉ thêm cột khi bảng rỗng. Không suy đoán EXACT/FUZZY/MANUAL cho dữ
liệu cũ hoặc tự nhận một cột đã được tạo ngoài lịch sử migration.
Ngừng nguồn ghi trước khi áp dụng vì MySQL DDL có implicit commit.
Downgrade bỏ cột source, do đó cần backup nếu đã có dữ liệu nguồn kỹ năng.
"""
from alembic import op
import sqlalchemy as sa


revision = "e95f3a7b8c41"
down_revision = "d84e2f6a7b30"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_context().as_sql:
        raise RuntimeError("CandidateSkill source migration requires an online schema/data preflight.")

    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table("candidate_skills"):
        raise RuntimeError("Missing candidate_skills table. Stop and inspect the schema.")
    columns = {column["name"] for column in inspector.get_columns("candidate_skills")}
    if not {"candidate_skill_id", "cv_id", "skill_id", "extracted_name"}.issubset(columns):
        raise RuntimeError("Unexpected candidate_skills schema. Stop before DDL.")
    if "source" in columns:
        raise RuntimeError("candidate_skills.source already exists. Verify schema drift before applying.")

    # Không gán nguồn giả cho kỹ năng đã có khi chưa có quyết định dữ liệu riêng.
    table = sa.table("candidate_skills", sa.column("candidate_skill_id", sa.Integer()))
    if connection.execute(sa.select(table.c.candidate_skill_id).limit(1)).first() is not None:
        raise RuntimeError(
            "Existing candidate_skills rows have no source. "
            "An explicitly approved legacy-data reconciliation is required before DDL."
        )

    # Default EXACT hiện nằm ở Model; không thêm server default khác với Model.
    op.add_column("candidate_skills", sa.Column(
        "source", sa.Enum("EXACT", "FUZZY", "MANUAL"), nullable=False
    ))


def downgrade():
    op.drop_column("candidate_skills", "source")
