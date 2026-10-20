from datetime import datetime

from sqlalchemy.dialects.mysql import LONGTEXT

from app.extensions import db


class CV(db.Model):
    # Tên bảng thật trong MySQL
    __tablename__ = "cvs"

    # Khóa chính của bảng CV
    cv_id = db.Column(db.Integer, primary_key=True)

    # Khóa ngoại: CV này thuộc User nào
    # Không unique vì 1 User có thể có nhiều CV
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id"),
        nullable=False
    )

    # Tên file CV gốc
    file_name = db.Column(db.String(255), nullable=False)

    # Đường dẫn đến nơi hệ thống lưu file CV
    file_path = db.Column(db.String(500), nullable=False)

    # Loại file: PDF hoặc DOCX
    file_type = db.Column(db.String(20), nullable=False)

    # Thời điểm upload CV
    uploaded_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    # PENDING / COMPLETED / FAILED
    analysis_status = db.Column(
        db.String(20),
        nullable=False,
        default="PENDING"
    )

    # Thời điểm CV được phân tích xong
    analyzed_at = db.Column(db.DateTime, nullable=True)

    # Nội dung chữ được trích xuất từ CV
    extracted_text = db.Column(LONGTEXT, nullable=True)