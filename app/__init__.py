from flask import Flask, session

from config import Config
from app.extensions import db, migrate, csrf, mail
from app.controllers.home_controller import home_bp
from app.controllers.auth_controller import auth_bp
from app.controllers.candidate_controller import candidate_bp
from app.controllers.recruiter_controller import recruiter_bp
from app.controllers.admin_controller import admin_bp
from app.controllers.public_jobs_controller import public_jobs_bp

def create_app():
    app = Flask(__name__)

    # Nạp cấu hình ứng dụng
    app.config.from_object(Config)

    # Khởi tạo SQLAlchemy
    db.init_app(app)

    # Khởi tạo chức năng gửi email cho ứng dụng
    mail.init_app(app)

    # Kết nối Flask-Migrate với app và database
    migrate.init_app(app, db)

    # Bật bảo vệ CSRF cho toàn bộ ứng dụng
    csrf.init_app(app)

    # Load toàn bộ Model để SQLAlchemy/Migration nhận diện các bảng
    from app import models


    @app.context_processor
    def inject_header_user():
        from app.models.user import User

        user_id = session.get("user_id")
        if not user_id:
            return {"header_user": None}

        user = db.session.get(User, user_id)
        if not user or user.user_status != "ACTIVE":
            return {"header_user": None}

        return {"header_user": user}

    # Đăng ký route của trang chủ
    app.register_blueprint(home_bp)

    # Đăng ký các route Authentication với Flask
    app.register_blueprint(auth_bp)

    # Đăng ký các đường dẫn dành cho Candidate.
    app.register_blueprint(candidate_bp)

    # Đăng ký các route dành cho Recruiter
    app.register_blueprint(recruiter_bp)

    # Đăng ký các route dành cho Admin
    app.register_blueprint(admin_bp)

    # Các trang việc làm công khai cho Guest và Candidate.
    app.register_blueprint(public_jobs_bp)

    return app