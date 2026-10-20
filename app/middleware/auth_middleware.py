from functools import wraps

from flask import session, flash, redirect, url_for

from app.services.auth_service import get_user_by_id


def login_required(view_function):
    """Chỉ cho phép User đã đăng nhập truy cập route."""

    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        # Lấy user_id của người đang đăng nhập từ session
        user_id = session.get("user_id")

        # Không có user_id → chưa đăng nhập
        if not user_id:
            flash("Vui lòng đăng nhập để tiếp tục.", "warning")
            return redirect(url_for("auth.login"))

        # Lấy User thật từ database, không chỉ tin dữ liệu trong session
        user = get_user_by_id(user_id)

        # Session có ID nhưng User không còn tồn tại
        if user is None:
            session.clear()
            flash("Phiên đăng nhập không hợp lệ.", "danger")
            return redirect(url_for("auth.login"))

        # Tài khoản đã bị khóa sau khi đăng nhập
        if user.user_status != "ACTIVE":
            session.clear()
            flash("Tài khoản hiện đang bị khóa.", "danger")
            return redirect(url_for("auth.login"))

        return view_function(*args, **kwargs)

    return wrapped_view


def role_required(*allowed_roles):
    """Chỉ cho phép các role được chỉ định truy cập route."""

    def decorator(view_function):
        @wraps(view_function)
        def wrapped_view(*args, **kwargs):
            # Route có phân quyền thì trước tiên phải đăng nhập
            user_id = session.get("user_id")

            if not user_id:
                flash("Vui lòng đăng nhập để tiếp tục.", "warning")
                return redirect(url_for("auth.login"))

            # Lấy role hiện tại trực tiếp từ User trong database
            user = get_user_by_id(user_id)

            if user is None:
                session.clear()
                flash("Phiên đăng nhập không hợp lệ.", "danger")
                return redirect(url_for("auth.login"))

            # Tài khoản bị khóa thì hủy luôn phiên đăng nhập
            if user.user_status != "ACTIVE":
                session.clear()
                flash("Tài khoản hiện đang bị khóa.", "danger")
                return redirect(url_for("auth.login"))

            # User tồn tại nhưng không thuộc role được phép
            if user.role not in allowed_roles:
                flash("Bạn không có quyền truy cập chức năng này.", "danger")
                return redirect(url_for("home.home"))

            return view_function(*args, **kwargs)

        return wrapped_view

    return decorator