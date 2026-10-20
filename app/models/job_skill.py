from app.extensions import db


class JobSkill(db.Model):
    # Tên bảng thật trong MySQL
    __tablename__ = "job_skills"

    # Khóa chính
    job_skill_id = db.Column(db.Integer, primary_key=True)

    # FK: kỹ năng này thuộc Job nào
    job_id = db.Column(
        db.Integer,
        db.ForeignKey("jobs.job_id"),
        nullable=False
    )

    # FK: Job đang yêu cầu Skill chuẩn nào
    skill_id = db.Column(
        db.Integer,
        db.ForeignKey("skills.skill_id"),
        nullable=False
    )

    # Mức độ yêu cầu:
    # REQUIRED = bắt buộc | PREFERRED = ưu tiên
    requirement_type = db.Column(
        db.String(20),
        nullable=False
    )

    # Trong cùng một Job, một Skill chỉ được xuất hiện một lần
    __table_args__ = (
        db.UniqueConstraint(
            "job_id",
            "skill_id",
            name="uq_job_skill_job_skill"
        ),
    )