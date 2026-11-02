#	Đăng ký, đăng nhập, OTP, quên mật khẩu, thông tin công ty khi đăng ký.
from datetime import datetime, timedelta
from urllib.parse import unquote, urlsplit
from werkzeug.exceptions import HTTPException

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    current_app
)

from app.services.auth_service import (
    register_user,
    generate_otp,
    hash_otp,
    check_otp,
    send_verification_otp,
    verify_user_email,
    get_user_by_id,
    create_recruiter_company,
    login_user,
    get_user_by_email,
    send_password_reset_otp,
    reset_user_password
)


auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/auth"
)


# Số lần tối đa được nhập sai OTP
MAX_OTP_ATTEMPTS = 5


def clear_otp_session():
    """Xóa toàn bộ dữ liệu OTP đang lưu tạm trong session."""

    session.pop("verify_user_id", None)
    session.pop("verify_otp", None)
    session.pop("verify_otp_expires_at", None)
    session.pop("resend_otp_available_at", None)
    session.pop("verify_otp_attempts", None)


def create_otp_session(user):
    """Tạo OTP mới, lưu dữ liệu xác thực và gửi email."""

    otp = generate_otp()

    # Lưu User đang cần xác thực
    session["verify_user_id"] = user.user_id

    # Chỉ lưu hash của OTP
    session["verify_otp"] = hash_otp(otp)

    # OTP có hiệu lực trong 5 phút
    session["verify_otp_expires_at"] = (
        datetime.now() + timedelta(minutes=5)
    ).isoformat()

    # Sau 60 giây mới được gửi lại
    session["resend_otp_available_at"] = (
        datetime.now() + timedelta(seconds=60)
    ).isoformat()

    # Bắt đầu với 0 lần nhập sai
    session["verify_otp_attempts"] = 0

    # OTP thật chỉ được gửi qua email
    send_verification_otp(user.email, otp)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Hiển thị và xử lý đăng ký Candidate/Recruiter."""

    if request.method == "GET":
        return render_template("auth/register.html")

    role = request.form.get("role", "CANDIDATE")
    user_name = request.form.get("user_name", "")
    email = request.form.get("email", "")
    phone = request.form.get("phone", "")
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    user, error = register_user(
        role=role,
        user_name=user_name,
        email=email,
        phone=phone,
        password=password,
        confirm_password=confirm_password
    )

    if error:
        flash(error, "danger")
        return render_template(
            "auth/register.html",
            role=role,
            user_name=user_name,
            email=email,
            phone=phone
        )

    # Xóa phiên OTP cũ trước khi tạo yêu cầu mới
    clear_otp_session()

    try:
        create_otp_session(user)

    except Exception:
        # Không để lại OTP session không sử dụng được
        clear_otp_session()

        flash(
            "Không thể gửi mã OTP. Vui lòng thử đăng ký lại.",
            "danger"
        )

        return render_template(
            "auth/register.html",
            role=role,
            user_name=user_name,
            email=email,
            phone=phone
        )

    flash(
        "Mã OTP đã được gửi đến email của bạn.",
        "success"
    )
    return redirect(url_for("auth.verify_email"))


@auth_bp.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    """Hiển thị trang nhập OTP và xác thực email."""

    user_id = session.get("verify_user_id")
    saved_otp_hash = session.get("verify_otp")
    expires_at = session.get("verify_otp_expires_at")

    # Không có phiên OTP hợp lệ
    if not user_id or not saved_otp_hash or not expires_at:
        flash(
            "Không tìm thấy yêu cầu xác thực. Vui lòng đăng ký lại.",
            "danger"
        )
        return redirect(url_for("auth.register"))

    if request.method == "GET":
        return render_template("auth/verify_otp.html")

    entered_otp = request.form.get("otp", "").strip()

    # OTP phải gồm đúng 6 chữ số
    if not entered_otp.isdigit() or len(entered_otp) != 6:
        flash("Mã OTP phải gồm 6 chữ số.", "danger")
        return render_template("auth/verify_otp.html")

    # OTP hết hạn → yêu cầu gửi OTP mới
    if datetime.now() > datetime.fromisoformat(expires_at):
        session.pop("verify_otp", None)
        session.pop("verify_otp_expires_at", None)
        session["verify_otp_attempts"] = 0

        flash(
            "Mã OTP đã hết hạn. Vui lòng gửi lại mã OTP mới.",
            "danger"
        )
        return render_template("auth/verify_otp.html")

    # Lấy số lần đã nhập sai
    attempts = session.get("verify_otp_attempts", 0)

    # Kiểm tra OTP
    if not check_otp(saved_otp_hash, entered_otp):
        attempts += 1
        session["verify_otp_attempts"] = attempts

        remaining_attempts = MAX_OTP_ATTEMPTS - attempts

        # Sai đủ 5 lần → vô hiệu OTP hiện tại
        if remaining_attempts <= 0:
            session.pop("verify_otp", None)
            session.pop("verify_otp_expires_at", None)

            flash(
                "Bạn đã nhập sai OTP quá 5 lần. "
                "Vui lòng gửi lại mã OTP mới.",
                "danger"
            )
            return render_template("auth/verify_otp.html")

        flash(
            f"Mã OTP không chính xác. "
            f"Bạn còn {remaining_attempts} lần thử.",
            "danger"
        )
        return render_template("auth/verify_otp.html")

    # OTP đúng → xác thực email
    if not verify_user_email(user_id):
        clear_otp_session()

        flash(
            "Không tìm thấy tài khoản cần xác thực.",
            "danger"
        )
        return redirect(url_for("auth.register"))

    user = get_user_by_id(user_id)

    if user is None:
        clear_otp_session()

        flash("Không tìm thấy tài khoản.", "danger")
        return redirect(url_for("auth.register"))

    # Xác thực hoàn tất → xóa OTP session
    clear_otp_session()

    # Recruiter phải hoàn thành thông tin Company
    if user.role == "RECRUITER":
        session["setup_recruiter_user_id"] = user.user_id

        flash(
            "Xác thực email thành công. "
            "Vui lòng nhập thông tin công ty.",
            "success"
        )
        return redirect(url_for("auth.recruiter_company"))

    # Candidate hoàn tất đăng ký
    flash("Xác thực email thành công.", "success")
    return redirect(url_for("home.home"))


@auth_bp.route("/resend-otp", methods=["POST"])
def resend_otp():
    """Tạo và gửi lại OTP cho User đang chờ xác thực."""

    user_id = session.get("verify_user_id")

    if not user_id:
        flash(
            "Không tìm thấy yêu cầu xác thực. Vui lòng đăng ký lại.",
            "danger"
        )
        return redirect(url_for("auth.register"))

    user = get_user_by_id(user_id)

    if user is None:
        clear_otp_session()

        flash(
            "Không tìm thấy tài khoản cần xác thực.",
            "danger"
        )
        return redirect(url_for("auth.register"))

    if user.email_verified:
        clear_otp_session()

        flash("Email này đã được xác thực.", "success")
        return redirect(url_for("home.home"))

    resend_available_at = session.get("resend_otp_available_at")

    # Kiểm tra cooldown gửi lại OTP
    if resend_available_at:
        available_at = datetime.fromisoformat(resend_available_at)

        if datetime.now() < available_at:
            remaining_seconds = int(
                (available_at - datetime.now()).total_seconds()
            ) + 1

            flash(
                f"Vui lòng chờ {remaining_seconds} giây "
                "trước khi gửi lại OTP.",
                "warning"
            )
            return redirect(url_for("auth.verify_email"))

    try:
        # Tạo OTP mới
        new_otp = generate_otp()

        # Gửi email trước
        send_verification_otp(user.email, new_otp)

        # Gửi thành công mới thay OTP cũ trong session
        session["verify_otp"] = hash_otp(new_otp)

        session["verify_otp_expires_at"] = (
            datetime.now() + timedelta(minutes=5)
        ).isoformat()

        session["resend_otp_available_at"] = (
            datetime.now() + timedelta(seconds=60)
        ).isoformat()

        # OTP mới → reset số lần nhập sai
        session["verify_otp_attempts"] = 0

    except Exception:
        flash(
            "Không thể gửi lại mã OTP. Vui lòng thử lại sau.",
            "danger"
        )
        return redirect(url_for("auth.verify_email"))

    flash(
        "Mã OTP mới đã được gửi đến email của bạn.",
        "success"
    )
    return redirect(url_for("auth.verify_email"))


@auth_bp.route("/register/recruiter/company", methods=["GET", "POST"])
def recruiter_company():
    """Hoàn tất thông tin Company của Recruiter."""

    user_id = session.get("setup_recruiter_user_id")

    if not user_id:
        flash(
            "Không tìm thấy phiên đăng ký nhà tuyển dụng.",
            "danger"
        )
        return redirect(url_for("auth.register"))

    # Kiểm tra lại User trước khi cho xem form
    user = get_user_by_id(user_id)

    if (
        user is None
        or user.role != "RECRUITER"
        or not user.email_verified
        or user.user_status != "ACTIVE"
    ):
        session.pop("setup_recruiter_user_id", None)

        flash(
            "Phiên đăng ký nhà tuyển dụng không hợp lệ.",
            "danger"
        )
        return redirect(url_for("auth.register"))

    if request.method == "GET":
        return render_template("auth/recruiter_company.html")

    company_name = request.form.get("company_name", "")
    address = request.form.get("address", "")
    website = request.form.get("website", "")
    description = request.form.get("description", "")

    company, error = create_recruiter_company(
        user_id=user_id,
        company_name=company_name,
        address=address,
        website=website,
        description=description
    )

    if error:
        flash(error, "danger")

        return render_template(
            "auth/recruiter_company.html",
            company_name=company_name,
            address=address,
            website=website,
            description=description
        )

    # Company đã tạo → không còn cần session đăng ký tạm
    session.pop("setup_recruiter_user_id", None)

    flash(
        "Đăng ký tài khoản nhà tuyển dụng thành công.",
        "success"
    )
    return redirect(url_for("home.home"))


def safe_login_next(value, role=None):
    """Chỉ nhận URL nội bộ thuộc các trang đã biết, không cho open redirect."""
    if not isinstance(value, str) or len(value) > 2048:
        return ""
    decoded = unquote(value)
    if any(ord(char) < 32 or ord(char) == 127 for char in decoded) or "\\" in decoded:
        return ""
    try:
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//"):
            return ""
        if "%" in parsed.path:
            return ""
        endpoint, _ = current_app.url_map.bind_to_environ(request.environ).match(parsed.path, method="GET")
    except (HTTPException, ValueError):
        return ""
    public = {"home.home", "public_jobs.index", "public_jobs.show"}
    roles = {
        "candidate.dashboard": "CANDIDATE", "candidate.my_cvs": "CANDIDATE",
        "candidate.saved_jobs": "CANDIDATE", "recruiter.dashboard": "RECRUITER",
        "admin.dashboard": "ADMIN",
    }
    if endpoint not in public and (endpoint not in roles or role and roles[endpoint] != role):
        return ""
    return value


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Hiển thị và xử lý đăng nhập."""

    source = request.form if request.method == "POST" else request.args
    next_url = safe_login_next(source.get("next", "")) if len(source.getlist("next")) <= 1 else ""
    if request.method == "GET":
        return render_template("auth/login.html", next_url=next_url)

    email = request.form.get("email", "")
    password = request.form.get("password", "")

    user, error = login_user(email, password)

    if error:
        flash(error, "danger")

        return render_template(
            "auth/login.html",
            email=email,
            next_url=next_url
        )

    # Xóa session cũ trước khi tạo phiên đăng nhập
    session.clear()

    # Chỉ lưu dữ liệu tối thiểu
    session["user_id"] = user.user_id
    session["role"] = user.role

    flash("Đăng nhập thành công.", "success")
    return redirect(safe_login_next(next_url, user.role) or url_for("home.home"))

# =========================
# QUÊN MẬT KHẨU
# =========================

def clear_reset_password_session():
    """Xóa toàn bộ dữ liệu tạm của quá trình quên mật khẩu."""

    session.pop("reset_user_id", None)
    session.pop("reset_otp", None)
    session.pop("reset_otp_expires_at", None)
    session.pop("reset_otp_attempts", None)
    session.pop("reset_otp_verified", None)

    # Xóa luôn thời gian chờ gửi lại OTP
    session.pop("reset_resend_otp_available_at", None)


def invalidate_reset_otp():
    """
    Vô hiệu OTP hiện tại nhưng vẫn giữ reset_user_id.
    Nhờ đó User có thể bấm gửi lại OTP mà không nhập email lại.
    """

    session.pop("reset_otp", None)
    session.pop("reset_otp_expires_at", None)
    session.pop("reset_otp_attempts", None)
    session.pop("reset_otp_verified", None)


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Nhận email và gửi OTP đặt lại mật khẩu."""

    if request.method == "GET":
        return render_template(
            "auth/forgot_password.html",
            step="email"
        )

    email = request.form.get("email", "").strip().lower()

    if not email:
        flash("Vui lòng nhập email.", "danger")

        return render_template(
            "auth/forgot_password.html",
            step="email"
        )

    user = get_user_by_email(email)

    # Chỉ tài khoản đã xác thực và đang hoạt động mới được reset mật khẩu
    if (
        user is None
        or not user.email_verified
        or user.user_status != "ACTIVE"
    ):
        flash(
            "Không thể thực hiện yêu cầu đặt lại mật khẩu với email này.",
            "danger"
        )

        return render_template(
            "auth/forgot_password.html",
            step="email",
            email=email
        )

    otp = generate_otp()

    try:
        # Gửi email trước, gửi thành công mới lưu OTP vào session
        send_password_reset_otp(user.email, otp)

    except Exception:
        flash(
            "Không thể gửi mã OTP. Vui lòng thử lại sau.",
            "danger"
        )

        return render_template(
            "auth/forgot_password.html",
            step="email",
            email=email
        )

    # Xóa yêu cầu reset cũ trước khi tạo yêu cầu mới
    clear_reset_password_session()

    # Ghi nhớ User đang đặt lại mật khẩu
    session["reset_user_id"] = user.user_id

    # Chỉ lưu hash của OTP, không lưu OTP thật
    session["reset_otp"] = hash_otp(otp)

    # OTP có hiệu lực trong 5 phút
    session["reset_otp_expires_at"] = (
        datetime.now() + timedelta(minutes=5)
    ).isoformat()

    # Sau 60 giây mới được gửi lại OTP
    session["reset_resend_otp_available_at"] = (
        datetime.now() + timedelta(seconds=60)
    ).isoformat()

    # Bắt đầu với 0 lần nhập sai
    session["reset_otp_attempts"] = 0

    flash(
        "Mã OTP đặt lại mật khẩu đã được gửi đến email của bạn.",
        "success"
    )

    return redirect(url_for("auth.verify_reset_otp"))


@auth_bp.route("/forgot-password/verify", methods=["GET", "POST"])
def verify_reset_otp():
    """Kiểm tra OTP của yêu cầu đặt lại mật khẩu."""

    user_id = session.get("reset_user_id")

    # Không còn User đang thực hiện quên mật khẩu
    if not user_id:
        flash(
            "Không tìm thấy yêu cầu đặt lại mật khẩu.",
            "danger"
        )

        return redirect(url_for("auth.forgot_password"))

    saved_otp_hash = session.get("reset_otp")
    expires_at = session.get("reset_otp_expires_at")

    # GET vẫn cho xem trang OTP dù OTP cũ đã bị vô hiệu.
    # User có thể bấm "Gửi lại mã OTP".
    if request.method == "GET":
        return render_template(
            "auth/forgot_password.html",
            step="otp"
        )

    # Không còn OTP hợp lệ nhưng vẫn còn User
    if not saved_otp_hash or not expires_at:
        flash(
            "Mã OTP hiện tại không còn hiệu lực. Vui lòng gửi lại mã OTP mới.",
            "warning"
        )

        return render_template(
            "auth/forgot_password.html",
            step="otp"
        )

    entered_otp = request.form.get("otp", "").strip()

    # OTP phải gồm đúng 6 chữ số
    if not entered_otp.isdigit() or len(entered_otp) != 6:
        flash("Mã OTP phải gồm 6 chữ số.", "danger")

        return render_template(
            "auth/forgot_password.html",
            step="otp"
        )

    # OTP đã quá 5 phút
    if datetime.now() > datetime.fromisoformat(expires_at):

        # Chỉ hủy OTP, vẫn giữ User để có thể gửi lại
        invalidate_reset_otp()

        flash(
            "Mã OTP đã hết hạn. Vui lòng gửi lại mã OTP mới.",
            "warning"
        )

        return render_template(
            "auth/forgot_password.html",
            step="otp"
        )

    attempts = session.get("reset_otp_attempts", 0)

    # OTP không chính xác
    if not check_otp(saved_otp_hash, entered_otp):

        attempts += 1
        session["reset_otp_attempts"] = attempts

        remaining_attempts = MAX_OTP_ATTEMPTS - attempts

        # Nhập sai đủ 5 lần → chỉ vô hiệu OTP hiện tại
        if remaining_attempts <= 0:

            invalidate_reset_otp()

            flash(
                "Bạn đã nhập sai OTP quá 5 lần. "
                "Vui lòng gửi lại mã OTP mới.",
                "danger"
            )

            return render_template(
                "auth/forgot_password.html",
                step="otp"
            )

        flash(
            f"Mã OTP không chính xác. "
            f"Bạn còn {remaining_attempts} lần thử.",
            "danger"
        )

        return render_template(
            "auth/forgot_password.html",
            step="otp"
        )

    # OTP đúng → không cần giữ OTP nữa
    session.pop("reset_otp", None)
    session.pop("reset_otp_expires_at", None)
    session.pop("reset_otp_attempts", None)
    session.pop("reset_resend_otp_available_at", None)

    # Đánh dấu User đã vượt qua bước xác thực OTP
    session["reset_otp_verified"] = True

    return redirect(url_for("auth.reset_password"))


@auth_bp.route("/forgot-password/resend-otp", methods=["POST"])
def resend_reset_otp():
    """Gửi lại OTP cho User đang thực hiện quên mật khẩu."""

    user_id = session.get("reset_user_id")

    # Không biết User nào đang yêu cầu reset
    if not user_id:
        flash(
            "Không tìm thấy yêu cầu đặt lại mật khẩu.",
            "danger"
        )

        return redirect(url_for("auth.forgot_password"))

    user = get_user_by_id(user_id)

    # Kiểm tra lại tài khoản trước khi gửi email
    if (
        user is None
        or not user.email_verified
        or user.user_status != "ACTIVE"
    ):
        clear_reset_password_session()

        flash(
            "Yêu cầu đặt lại mật khẩu không còn hợp lệ.",
            "danger"
        )

        return redirect(url_for("auth.forgot_password"))

    resend_available_at = session.get(
        "reset_resend_otp_available_at"
    )

    # Kiểm tra đã đủ 60 giây chưa
    if resend_available_at:

        available_at = datetime.fromisoformat(
            resend_available_at
        )

        if datetime.now() < available_at:

            remaining_seconds = int(
                (available_at - datetime.now()).total_seconds()
            ) + 1

            flash(
                f"Vui lòng chờ {remaining_seconds} giây "
                "trước khi gửi lại OTP.",
                "warning"
            )

            return redirect(
                url_for("auth.verify_reset_otp")
            )

    new_otp = generate_otp()

    try:
        # Gửi OTP mới qua email
        send_password_reset_otp(
            user.email,
            new_otp
        )

    except Exception:
        flash(
            "Không thể gửi lại mã OTP. Vui lòng thử lại sau.",
            "danger"
        )

        return redirect(
            url_for("auth.verify_reset_otp")
        )

    # Gửi email thành công mới thay OTP cũ
    session["reset_otp"] = hash_otp(new_otp)

    # OTP mới tiếp tục có hiệu lực 5 phút
    session["reset_otp_expires_at"] = (
        datetime.now() + timedelta(minutes=5)
    ).isoformat()

    # Sau lần gửi này phải chờ tiếp 60 giây
    session["reset_resend_otp_available_at"] = (
        datetime.now() + timedelta(seconds=60)
    ).isoformat()

    # OTP mới → cho lại 5 lần nhập
    session["reset_otp_attempts"] = 0

    # OTP mới chưa được xác thực
    session.pop("reset_otp_verified", None)

    flash(
        "Mã OTP mới đã được gửi đến email của bạn.",
        "success"
    )

    return redirect(url_for("auth.verify_reset_otp"))


@auth_bp.route("/forgot-password/reset", methods=["GET", "POST"])
def reset_password():
    """Đặt mật khẩu mới sau khi User đã xác thực OTP."""

    user_id = session.get("reset_user_id")
    otp_verified = session.get("reset_otp_verified")

    # Không cho truy cập trực tiếp nếu chưa xác thực OTP
    if not user_id or not otp_verified:
        flash(
            "Vui lòng xác thực OTP trước khi đặt lại mật khẩu.",
            "danger"
        )

        return redirect(url_for("auth.forgot_password"))

    if request.method == "GET":
        return render_template(
            "auth/forgot_password.html",
            step="reset"
        )

    password = request.form.get("password", "")
    confirm_password = request.form.get(
        "confirm_password",
        ""
    )

    success, error = reset_user_password(
        user_id=user_id,
        password=password,
        confirm_password=confirm_password
    )

    if not success:
        flash(error, "danger")

        return render_template(
            "auth/forgot_password.html",
            step="reset"
        )

    # Reset thành công → xóa toàn bộ dữ liệu reset tạm
    clear_reset_password_session()

    flash(
        "Đặt lại mật khẩu thành công. Vui lòng đăng nhập.",
        "success"
    )

    return redirect(url_for("auth.login"))

@auth_bp.route("/logout", methods=["POST"])
def logout():
    """Đăng xuất User hiện tại."""

    session.clear()

    flash("Đăng xuất thành công.", "success")
    return redirect(url_for("home.home"))
