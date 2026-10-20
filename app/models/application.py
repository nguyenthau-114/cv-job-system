from datetime import datetime

from app.extensions import db


class Application(db.Model):
    # Tên bảng thật trong MySQL
    __tablename__ = "applications"

    # Khóa chính của hồ sơ ứng tuyển
    application_id = db.Column(db.Integer, primary_key=True)

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

    # Email để nhà tuyển dụng liên hệ với ứng viên
    contact_email = db.Column(
        db.String(255),
        nullable=False
    )

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