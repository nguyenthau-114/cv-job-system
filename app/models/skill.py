from datetime import datetime

from app.extensions import db


class Skill(db.Model):
    # Tên bảng thật trong MySQL
    __tablename__ = "skills"

    # Khóa chính của bảng Skill
    skill_id = db.Column(db.Integer, primary_key=True)

    # Tên kỹ năng chuẩn, không được trùng nhau
    # Ví dụ: Java, Python, MySQL, JavaScript
    skill_name = db.Column(
        db.String(100),
        nullable=False,
        unique=True
    )

    # ACTIVE: đang sử dụng | INACTIVE: ngừng sử dụng
    skill_status = db.Column(
        db.String(20),
        nullable=False,
        default="ACTIVE"
    )

    # Thời điểm kỹ năng được thêm vào hệ thống
    skill_created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )