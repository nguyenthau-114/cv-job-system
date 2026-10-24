from datetime import datetime

from app.extensions import db


class Application(db.Model):
    # Tên bảng thật trong MySQL
    __tablename__ = "applications"

    # Khóa chính của hồ sơ ứng tuyển
    application_id = db.Column(db.Integer, primary_key=True)

    # Candidate sở hữu đơn, dùng để chống nộp trùng dù thay đổi CV.
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", name="fk_application_user_id_users"),
        nullable=False
    )

    # FK: ứng viên đã dùng CV nào để ứng tuyển
    cv_id = db.Column(
        db.Integer,
        db.ForeignKey("cvs.cv_id"),
        nullable=False
    )

    # FK: ứng tuyển vào Job nào
    job_id = db.Column(
        db.Integer,
        db.ForeignKey("jobs.job_id"),
        nullable=False
    )

    # Thông tin liên hệ riêng của đơn, không đồng bộ ngược vào tài khoản.
    contact_name = db.Column(db.String(100), nullable=False)

    # Email để nhà tuyển dụng liên hệ với ứng viên
    contact_email = db.Column(
        db.String(255),
        nullable=False
    )

    contact_phone = db.Column(db.String(20), nullable=False)
    cover_letter = db.Column(db.Text, nullable=True)

    # SUBMITTED / VIEWED / CONSIDERING /
    # INTERVIEW / REJECTED / WITHDRAWN
    application_status = db.Column(
        db.String(30),
        nullable=False,
        default="SUBMITTED"
    )

    # Thời điểm ứng viên nộp hồ sơ
    applied_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    # Chỉ có giá trị khi ứng viên rút hồ sơ
    withdrawn_at = db.Column(
        db.DateTime,
        nullable=True
    )

    # Hồ sơ đã rút vẫn giữ ràng buộc một Candidate chỉ ứng tuyển một lần/Job.
    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "job_id", name="uq_application_user_job"
        ),
    )
