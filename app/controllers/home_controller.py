from flask import Blueprint, render_template, session

from app.services.auth_service import get_user_by_id
from app.middleware.auth_middleware import role_required

home_bp = Blueprint("home", __name__)


@home_bp.route("/")
def home():
    """Hiển thị trang chủ và nhận biết User đang đăng nhập."""

    # Lấy user_id đã lưu trong session khi đăng nhập
    user_id = session.get("user_id")

    # Mặc định là chưa có người dùng đăng nhập
    user = None

    # Nếu có session đăng nhập → lấy User thật từ database
    if user_id:
        user = get_user_by_id(user_id)

    # Gửi thông tin User sang home.html
    return render_template("home.html", user=user)
