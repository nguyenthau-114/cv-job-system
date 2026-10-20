from datetime import datetime

from app.extensions import db


class Company(db.Model):
    # Tên bảng thật trong MySQL
    __tablename__ = "companies"

    # Khóa chính của bảng companies
    company_id = db.Column(db.Integer, primary_key=True)

    # FK liên kết Company với User
    # unique=True đảm bảo 1 User chỉ có tối đa 1 Company
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id"),
        nullable=False,
        unique=True
    )

    company_name = db.Column(db.String(150), nullable=False)
    logo = db.Column(db.String(255), nullable=True)
    company_description = db.Column(db.Text, nullable=True)
    address = db.Column(db.String(255), nullable=True)
    website = db.Column(db.String(255), nullable=True)

    # Tự lưu thời điểm Company được tạo
    company_created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )