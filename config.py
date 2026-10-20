import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Khóa bí mật Flask dùng để bảo vệ session, flash message,...
    SECRET_KEY = os.getenv("SECRET_KEY")

    # Chuỗi kết nối tới MySQL
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{os.getenv('DB_USER')}:"
        f"{os.getenv('DB_PASSWORD')}@"
        f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/"
        f"{os.getenv('DB_NAME')}"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Cấu hình máy chủ Gmail dùng để gửi email
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "True").lower() == "true"

    MAIL_DEBUG = False

    # Tài khoản Gmail và App Password lấy từ .env
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")

    # Địa chỉ mặc định dùng để gửi email từ hệ thống
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_USERNAME")

    # Thư mục lưu CV mà Candidate tải lên.
    UPLOAD_CV_FOLDER = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "uploads",
        "cvs"
    )

    # Giới hạn toàn bộ request upload tối đa 10 MB.
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    # Giới hạn tài nguyên khi phân tích CV
    MAX_CV_PDF_PAGES = 20
    MAX_CV_IMAGE_PIXELS = 20_000_000
    CV_OCR_TIMEOUT = 30