import re
import secrets

from flask_mail import Message
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db, mail
from app.models.user import User
from app.models.company import Company

def validate_password(password):
    """Kiểm tra quy tắc mật khẩu dùng chung cho toàn hệ thống."""

    if len(password) < 8:
        return "Mật khẩu phải có ít nhất 8 ký tự."

    if not re.search(r"[A-Z]", password):
        return "Mật khẩu phải có ít nhất 1 chữ hoa."

    if not re.search(r"[a-z]", password):
        return "Mật khẩu phải có ít nhất 1 chữ thường."

    if not re.search(r"\d", password):
        return "Mật khẩu phải có ít nhất 1 chữ số."

    return None

def register_user(
    role,
    user_name,
    email,
    phone,
    password,
    confirm_password
):
    """
    Kiểm tra dữ liệu và tạo tài khoản Candidate hoặc Recruiter.
    Nếu email tồn tại nhưng chưa xác thực thì cập nhật lại tài khoản đó.
    """

    # Chuẩn hóa dữ liệu người dùng nhập
    role = role.strip().upper() if role else ""
    user_name = user_name.strip()
    email = email.strip().lower()
    phone = phone.strip() if phone else ""

    # Không tin role gửi từ trình duyệt
    if role not in ("CANDIDATE", "RECRUITER"):
        return None, "Loại tài khoản không hợp lệ."

    # Kiểm tra các trường bắt buộc
    if not user_name:
        return None, "Vui lòng nhập họ tên."

    if not email:
        return None, "Vui lòng nhập email."

    if not password:
        return None, "Vui lòng nhập mật khẩu."

    if not confirm_password:
        return None, "Vui lòng xác nhận mật khẩu."

    # Kiểm tra định dạng email cơ bản
    email_pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

    if not re.fullmatch(email_pattern, email):
        return None, "Email không đúng định dạng."

    # Số điện thoại không bắt buộc, nhưng nếu nhập phải hợp lệ
    if phone and not re.fullmatch(r"\d{10,11}", phone):
        return None, "Số điện thoại phải gồm 10 đến 11 chữ số."

    # Kiểm tra mật khẩu theo quy tắc chung
    password_error = validate_password(password)

    if password_error:
        return None, password_error

    if password != confirm_password:
        return None, "Mật khẩu xác nhận không khớp."

    # Kiểm tra email trong database
    existing_user = User.query.filter_by(email=email).first()

    # Email đã xác thực thì không được đăng ký lại
    if existing_user is not None and existing_user.email_verified:
        return None, "Email này đã được sử dụng."

    try:
        if existing_user is not None:
            # Email tồn tại nhưng chưa xác thực:
            # cập nhật lại dữ liệu thay vì tạo User trùng email
            existing_user.user_name = user_name
            existing_user.phone = phone if phone else None
            existing_user.role = role
            existing_user.user_status = "ACTIVE"

            # Hash mật khẩu thông qua User Model
            existing_user.set_password(password)

            db.session.commit()
            return existing_user, None

        # Tạo User mới
        new_user = User(
            user_name=user_name,
            email=email,
            phone=phone if phone else None,
            role=role,
            user_status="ACTIVE",
            email_verified=False
        )

        # Hash mật khẩu trước khi lưu database
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        return new_user, None

    except Exception:
        # Nếu database gặp lỗi thì hoàn tác transaction
        db.session.rollback()
        return None, "Không thể tạo tài khoản. Vui lòng thử lại."


def generate_otp():
    """Tạo mã OTP ngẫu nhiên gồm 6 chữ số."""

    return str(secrets.randbelow(900000) + 100000)


def hash_otp(otp):
    """Hash OTP trước khi lưu vào session."""

    return generate_password_hash(otp)


def check_otp(otp_hash, entered_otp):
    """Kiểm tra OTP người dùng nhập với OTP đã hash."""

    return check_password_hash(otp_hash, entered_otp)


def verify_user_email(user_id):
    """Đánh dấu email của User là đã xác thực."""

    user = db.session.get(User, user_id)

    if user is None:
        return False

    try:
        user.email_verified = True
        db.session.commit()
        return True

    except Exception:
        db.session.rollback()
        return False


def send_verification_otp(email, otp):
    """Gửi mã OTP xác thực tài khoản đến email người dùng."""

    message = Message(
        subject="Mã xác thực tài khoản JobFit",
        recipients=[email]
    )

    message.body = (
        "Xin chào,\n\n"
        f"Mã OTP xác thực tài khoản JobFit của bạn là: {otp}\n\n"
        "Mã này có hiệu lực trong 5 phút.\n"
        "Nếu bạn không thực hiện đăng ký, vui lòng bỏ qua email này."
    )

    # Nếu gửi email lỗi, Controller sẽ xử lý exception
    mail.send(message)


def get_user_by_id(user_id):
    """Tìm User theo ID."""

    return db.session.get(User, user_id)


def get_user_by_email(email):
    """Tìm User theo email."""

    email = email.strip().lower() if email else ""

    if not email:
        return None

    return User.query.filter_by(email=email).first()


def create_recruiter_company(
    user_id,
    company_name,
    address,
    website,
    description
):
    """Kiểm tra dữ liệu và tạo Company cho Recruiter."""

    company_name = company_name.strip()
    address = address.strip()
    website = website.strip() if website else ""
    description = description.strip() if description else ""

    if not company_name:
        return None, "Vui lòng nhập tên công ty."

    if not address:
        return None, "Vui lòng nhập địa chỉ công ty."

    # Website không bắt buộc, nhưng nếu nhập phải bắt đầu bằng http/https
    if website and not re.match(r"^https?://", website, re.IGNORECASE):
        return None, "Website phải bắt đầu bằng http:// hoặc https://."

    user = db.session.get(User, user_id)

    if user is None:
        return None, "Không tìm thấy tài khoản nhà tuyển dụng."

    if user.role != "RECRUITER":
        return None, "Tài khoản không có quyền tạo thông tin công ty."

    if not user.email_verified:
        return None, "Vui lòng xác thực email trước."

    if user.user_status != "ACTIVE":
        return None, "Tài khoản hiện đang bị khóa."

    # Một Recruiter chỉ có tối đa một Company
    existing_company = Company.query.filter_by(user_id=user_id).first()

    if existing_company is not None:
        return None, "Tài khoản này đã có thông tin công ty."

    company = Company(
        user_id=user_id,
        company_name=company_name,
        address=address,
        website=website if website else None,
        company_description=description if description else None
    )

    try:
        db.session.add(company)
        db.session.commit()

        return company, None

    except Exception:
        db.session.rollback()
        return None, "Không thể lưu thông tin công ty. Vui lòng thử lại."


def login_user(email, password):
    """Kiểm tra email và mật khẩu để đăng nhập."""

    email = email.strip().lower()

    if not email or not password:
        return None, "Vui lòng nhập email và mật khẩu."

    user = User.query.filter_by(email=email).first()

    # Không tiết lộ email có tồn tại hay không
    if user is None or not user.check_password(password):
        return None, "Email hoặc mật khẩu không chính xác."

    if not user.email_verified:
        return None, "Email chưa được xác thực."

    if user.user_status != "ACTIVE":
        return None, "Tài khoản hiện đang bị khóa."

    return user, None


def send_password_reset_otp(email, otp):
    """Gửi mã OTP dùng để đặt lại mật khẩu."""

    message = Message(
        subject="Mã đặt lại mật khẩu JobFit",
        recipients=[email]
    )

    message.body = (
        "Xin chào,\n\n"
        f"Mã OTP đặt lại mật khẩu JobFit của bạn là: {otp}\n\n"
        "Mã này có hiệu lực trong 5 phút.\n"
        "Nếu bạn không yêu cầu đặt lại mật khẩu, "
        "vui lòng bỏ qua email này."
    )

    # Nếu gửi email lỗi, Controller sẽ xử lý exception
    mail.send(message)


def reset_user_password(user_id, password, confirm_password):
    """Kiểm tra và cập nhật mật khẩu mới cho User."""

    # Kiểm tra các trường bắt buộc
    if not password:
        return False, "Vui lòng nhập mật khẩu mới."

    if not confirm_password:
        return False, "Vui lòng xác nhận mật khẩu mới."

    # Mật khẩu mới phải tuân theo cùng quy tắc khi đăng ký
    if len(password) < 8:
        return False, "Mật khẩu phải có ít nhất 8 ký tự."

    if not re.search(r"[A-Z]", password):
        return False, "Mật khẩu phải có ít nhất 1 chữ hoa."

    if not re.search(r"[a-z]", password):
        return False, "Mật khẩu phải có ít nhất 1 chữ thường."

    if not re.search(r"\d", password):
        return False, "Mật khẩu phải có ít nhất 1 chữ số."

    if password != confirm_password:
        return False, "Mật khẩu xác nhận không khớp."

    user = db.session.get(User, user_id)

    if user is None:
        return False, "Không tìm thấy tài khoản."

    # Chỉ tài khoản đã xác thực email mới được đặt lại mật khẩu
    if not user.email_verified:
        return False, "Email chưa được xác thực."

    if user.user_status != "ACTIVE":
        return False, "Tài khoản hiện đang bị khóa."

    try:
        # User Model sẽ hash mật khẩu trước khi lưu
        user.set_password(password)
        db.session.commit()

        return True, None

    except Exception:
        db.session.rollback()
        return False, "Không thể đặt lại mật khẩu. Vui lòng thử lại."

