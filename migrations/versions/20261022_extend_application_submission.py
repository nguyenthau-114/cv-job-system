"""Add candidate identity and contact snapshots to applications.

Revision ID: a22f6b9d3e02
Revises: c21e4d8f6a01

Apply only with application writers stopped: MySQL DDL commits implicitly.
Legacy contact snapshots use the current account name/phone, not historical values.
"""
from alembic import op
import sqlalchemy as sa


revision = "a22f6b9d3e02"
down_revision = "c21e4d8f6a01"
branch_labels = None
depends_on = None


def _prepare_existing_applications(connection):
    """Kiểm tra toàn bộ dữ liệu cũ trước DDL, không dùng Model của ứng dụng."""
    applications = sa.table(
        "applications",
        sa.column("application_id", sa.Integer()),
        sa.column("cv_id", sa.Integer()),
        sa.column("job_id", sa.Integer()),
    )
    cvs = sa.table(
        "cvs", sa.column("cv_id", sa.Integer()), sa.column("user_id", sa.Integer())
    )
    users = sa.table(
        "users",
        sa.column("user_id", sa.Integer()),
        sa.column("user_name", sa.String(100)),
        sa.column("phone", sa.String(20)),
    )
    jobs = sa.table("jobs", sa.column("job_id", sa.Integer()))
    query = sa.select(
        applications.c.application_id,
        applications.c.job_id,
        users.c.user_id,
        users.c.user_name,
        users.c.phone,
        jobs.c.job_id.label("existing_job_id"),
    ).select_from(
        applications.outerjoin(cvs, applications.c.cv_id == cvs.c.cv_id)
        .outerjoin(users, cvs.c.user_id == users.c.user_id)
        .outerjoin(jobs, applications.c.job_id == jobs.c.job_id)
    )

    prepared = []
    seen = set()
    invalid_references = duplicate_pairs = invalid_contacts = 0
    for row in connection.execute(query).mappings():
        if row["user_id"] is None or row["existing_job_id"] is None:
            invalid_references += 1
            continue
        pair = (row["user_id"], row["job_id"])
        if pair in seen:
            duplicate_pairs += 1
        seen.add(pair)

        name = (row["user_name"] or "").strip()
        phone = (row["phone"] or "").strip()
        if not 1 <= len(name) <= 100 or not 1 <= len(phone) <= 20:
            invalid_contacts += 1
            continue
        # Chỉ lấy dữ liệu thực đang có; không sửa email hoặc các trường cũ.
        prepared.append({
            "legacy_id": row["application_id"],
            "legacy_user_id": row["user_id"],
            "legacy_name": name,
            "legacy_phone": phone,
        })

    if invalid_references or duplicate_pairs or invalid_contacts:
        # Chỉ báo số lượng, không tiết lộ thông tin liên hệ cá nhân.
        raise RuntimeError(
            "Application migration stopped before DDL: "
            f"missing CV/User/Job references={invalid_references}, "
            f"duplicate Candidate-Job rows={duplicate_pairs}, "
            f"missing or oversized contact name/phone={invalid_contacts}. "
            "Review legacy data explicitly; no rows were deleted, merged or fabricated."
        )
    return prepared


def upgrade():
    if op.get_context().as_sql:
        raise RuntimeError(
            "Application migration requires an online data preflight; "
            "offline SQL generation is not supported."
        )
    connection = op.get_bind()
    prepared = _prepare_existing_applications(connection)

    # Thêm cột nullable tạm để điền dữ liệu thực trước khi siết NOT NULL.
    op.add_column("applications", sa.Column("user_id", sa.Integer(), nullable=True))
    op.add_column("applications", sa.Column("contact_name", sa.String(100), nullable=True))
    op.add_column("applications", sa.Column("contact_phone", sa.String(20), nullable=True))
    op.add_column("applications", sa.Column("cover_letter", sa.Text(), nullable=True))

    if prepared:
        applications = sa.table(
            "applications",
            sa.column("application_id", sa.Integer()),
            sa.column("user_id", sa.Integer()),
            sa.column("contact_name", sa.String(100)),
            sa.column("contact_phone", sa.String(20)),
        )
        connection.execute(
            applications.update()
            .where(applications.c.application_id == sa.bindparam("legacy_id"))
            .values(
                user_id=sa.bindparam("legacy_user_id"),
                contact_name=sa.bindparam("legacy_name"),
                contact_phone=sa.bindparam("legacy_phone"),
            ),
            prepared,
        )

    with op.batch_alter_table("applications") as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("contact_name", existing_type=sa.String(100), nullable=False)
        batch_op.alter_column("contact_phone", existing_type=sa.String(20), nullable=False)
        batch_op.create_foreign_key(
            "fk_application_user_id_users", "users", ["user_id"], ["user_id"]
        )
        batch_op.create_unique_constraint(
            "uq_application_user_job", ["user_id", "job_id"]
        )


def downgrade():
    # Chỉ định nghĩa chiều hạ cấp, không tự gọi khi upgrade thất bại.
    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_constraint("uq_application_user_job", type_="unique")
        batch_op.drop_constraint("fk_application_user_id_users", type_="foreignkey")
        batch_op.drop_column("cover_letter")
        batch_op.drop_column("contact_phone")
        batch_op.drop_column("contact_name")
        batch_op.drop_column("user_id")
