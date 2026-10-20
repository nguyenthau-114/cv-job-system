from datetime import datetime

from app.extensions import db


class InterviewInvitation(db.Model):
    # Tên bảng thật trong MySQL
    __tablename__ = "interview_invitations"

    # Khóa chính
    interview_invitation_id = db.Column(
        db.Integer,
        primary_key=True
    )

    # FK: lời mời phỏng vấn này thuộc Application nào
    # unique=True vì mỗi Application tối đa 1 lời mời phỏng vấn
    application_id = db.Column(
        db.Integer,
        db.ForeignKey("applications.application_id"),
        nullable=False,
        unique=True
    )

    # Ngày phỏng vấn
    interview_date = db.Column(
        db.Date,
        nullable=False
    )

    # Giờ phỏng vấn
    interview_time = db.Column(
        db.Time,
        nullable=False
    )

    # ONLINE / IN_PERSON
    interview_mode = db.Column(
        db.String(20),
        nullable=False
    )

    # Địa điểm phỏng vấn trực tiếp
    interview_location = db.Column(
        db.String(255),
        nullable=True
    )

    # Link phỏng vấn online
    interview_link = db.Column(
        db.String(500),
        nullable=True
    )

    # Ghi chú thêm của nhà tuyển dụng
    note = db.Column(
        db.Text,
        nullable=True
    )

    # Thời điểm tạo lời mời
    invitation_created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )