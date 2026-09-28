from flask import Flask

from config import Config
from app.extensions import db
from app.controllers.home_controller import home_bp


def create_app():
    app = Flask(__name__)

    # Nạp cấu hình
    app.config.from_object(Config)

    # Khởi tạo các extension
    db.init_app(app)

    # Đăng ký Controller
    app.register_blueprint(home_bp)

    return app