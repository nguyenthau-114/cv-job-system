from datetime import datetime

from app.extensions import db


class Notification(db.Model):
    # Tên bảng thật trong MySQL
    __tablename__ = "notifications"

    # Khóa chính
    notification_id = db.Column(
        db.Integer,
        primary_key=True
    )

    # FK: thông báo này được gửi cho User nào
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id"),
        nullable=False
    )

    # FK: thông báo có thể liên quan đến một Application
    # Cho phép NULL vì không phải thông báo nào cũng liên quan đến ứng tuyển
    application_id = db.Column(
        db.Integer,
        db.ForeignKey("applications.application_id"),
        nullable=True
    )

    job_id = db.Column(db.Integer, db.ForeignKey("jobs.job_id", name="fk_notification_job_id_jobs"), nullable=True)
    event_type = db.Column(db.String(40), nullable=False)
    event_key = db.Column(db.String(160), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("user_id", "event_key", name="uq_notification_user_event"),
        db.Index("ix_notification_user_latest", "user_id", "notification_id"),
        db.Index("ix_notification_user_unread", "user_id", "is_read", "notification_id"),
    )

    # Nội dung thông báo
    notification_message = db.Column(
        db.String(500),
        nullable=False
    )

    # False = chưa đọc | True = đã đọc
    is_read = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    # Thời điểm tạo thông báo
    notification_created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )
