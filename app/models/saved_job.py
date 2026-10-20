from datetime import datetime

from app.extensions import db


class SavedJob(db.Model):
    # Tên bảng thật trong MySQL
    __tablename__ = "saved_jobs"

    # Khóa chính
    saved_job_id = db.Column(db.Integer, primary_key=True)

    # FK: User nào đã lưu công việc này
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id"),
        nullable=False
    )

    # FK: Job nào được lưu
    job_id = db.Column(
        db.Integer,
        db.ForeignKey("jobs.job_id"),
        nullable=False
    )

    # Thời điểm User lưu Job
    saved_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    # Một User chỉ được lưu cùng một Job một lần
    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "job_id",
            name="uq_saved_job_user_job"
        ),
    )