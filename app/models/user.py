from datetime import datetime

from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db


class User(db.Model):
    # Tên bảng thật được tạo trong MySQL
    __tablename__ = "users"

    # Khóa chính, Integer PK sẽ tự tăng trong MySQL
    user_id = db.Column(db.Integer, primary_key=True)

    user_name = db.Column(db.String(100), nullable=False)

    # Email dùng đăng nhập nên không được trùng; index giúp tìm theo email nhanh hơn
    email = db.Column(
        db.String(255),
        unique=True,
        nullable=False,
        index=True
    )

    # Chỉ lưu mật khẩu đã băm, không lưu mật khẩu gốc
    password_hash = db.Column(db.String(255), nullable=False)

    phone = db.Column(db.String(20), nullable=True)
    avatar = db.Column(db.String(255), nullable=True)

    # CANDIDATE / RECRUITER / ADMIN
    role = db.Column(db.String(20), nullable=False)

    # ACTIVE / LOCKED
    user_status = db.Column(
        db.String(20),
        nullable=False,
        default="ACTIVE"
    )

    # False: chưa xác thực email | True: đã xác thực
    email_verified = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    # Tự lưu thời điểm tạo tài khoản
    user_created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    # Băm mật khẩu trước khi lưu xuống database
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    # So sánh mật khẩu người dùng nhập với mật khẩu đã băm
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)