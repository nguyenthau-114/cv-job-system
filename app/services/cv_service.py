import os
import uuid
import zipfile

import pymupdf
import pytesseract
from docx import Document
from flask import current_app
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.cv import CV
from app.models.application import Application
from app.models.candidate_skill import CandidateSkill
from app.models.user import User


# Đường dẫn Tesseract OCR đã cài trên Windows.
pytesseract.pytesseract.tesseract_cmd = (
    r"D:\ThuMucTaiXuong_app_code\App scan CV sang text\tesseract.exe"
)

# Các định dạng CV được phép tải lên.
ALLOWED_CV_EXTENSIONS = {"pdf", "docx", "jpg", "jpeg", "png"}


def is_valid_cv_content(file, extension):
    """Kiểm tra nội dung file có đúng định dạng được phép hay không."""

    # Đưa con trỏ về đầu file trước khi kiểm tra.
    file.stream.seek(0)

    if extension == "pdf":
        # Kiểm tra chữ ký cơ bản của file PDF.
        header = file.stream.read(5)
        file.stream.seek(0)
        return header == b"%PDF-"

    if extension == "docx":
        try:
            # DOCX là file ZIP chứa các thành phần tài liệu Word.
            with zipfile.ZipFile(file.stream) as docx_zip:
                file_names = set(docx_zip.namelist())

                valid = (
                    "[Content_Types].xml" in file_names
                    and "word/document.xml" in file_names
                )

        except (zipfile.BadZipFile, OSError):
            valid = False

        finally:
            # Đưa con trỏ về đầu để lưu file đầy đủ.
            file.stream.seek(0)

        return valid

    if extension in {"jpg", "jpeg", "png"}:
        try:
            with Image.open(file.stream) as image:
                actual_format = image.format
                max_pixels = current_app.config["MAX_CV_IMAGE_PIXELS"]

                if image.width * image.height > max_pixels:
                    return False

                image.verify()

            # Kiểm tra định dạng ảnh có khớp phần mở rộng.
            if extension in {"jpg", "jpeg"}:
                valid = actual_format == "JPEG"
            else:
                valid = actual_format == "PNG"

        except (UnidentifiedImageError, OSError):
            valid = False

        finally:
            file.stream.seek(0)

        return valid

    return False


def get_user_cvs(user_id):
    """Lấy tất cả CV của User đang đăng nhập."""

    return (
        CV.query
        .filter_by(user_id=user_id)
        .order_by(CV.uploaded_at.desc())
        .all()
    )


def set_cv_visibility(user_id, cv_id, is_hidden):
    """Chỉ ẩn khi mọi đơn tham chiếu đã kết thúc, luôn cho phép hiện lại CV."""
    if type(is_hidden) is not bool:
        return False, "Trạng thái ẩn CV không hợp lệ."
    try:
        user = User.query.filter_by(user_id=user_id).populate_existing().with_for_update().first()
        if user is None or user.role != "CANDIDATE" or user.user_status != "ACTIVE":
            db.session.rollback()
            return False, "Chỉ Candidate đang hoạt động được ẩn hoặc hiện CV."
        cv = CV.query.filter_by(cv_id=cv_id, user_id=user_id).populate_existing().with_for_update().first()
        if cv is None:
            db.session.rollback()
            return False, "Không tìm thấy CV hoặc bạn không có quyền thay đổi."
        if is_hidden:
            # Khóa User → CV → Application; đọc trực tiếp trạng thái mới nhất từ DB.
            applications = db.session.query(Application.application_status).filter(
                Application.cv_id == cv_id
            ).order_by(Application.application_id).with_for_update().all()
            # So sánh chính xác tại Python, không phụ thuộc collation hoặc bỏ lọt NULL.
            if any(row.application_status not in {"REJECTED", "WITHDRAWN"} for row in applications):
                db.session.rollback()
                return False, "Không thể ẩn CV vì còn hồ sơ ứng tuyển chưa kết thúc hoặc có trạng thái không hợp lệ."
        if cv.is_hidden == is_hidden:
            db.session.rollback()
        else:
            cv.is_hidden = is_hidden
            db.session.commit()
        return True, "Đã ẩn CV." if is_hidden else "Đã hiện CV."
    except SQLAlchemyError as error:
        db.session.rollback()
        current_app.logger.error("Không thể đổi trạng thái ẩn CV (%s).", type(error).__name__)
        return False, "Không thể thay đổi trạng thái CV. Vui lòng thử lại."


def get_user_cv(user_id, cv_id):
    """Lấy CV thuộc đúng Candidate đang đăng nhập."""

    # Kiểm tra cả CV và chủ sở hữu.
    return CV.query.filter_by(
        cv_id=cv_id,
        user_id=user_id
    ).first()



def extract_pdf_text(file_path):
    """Trích xuất PDF với giới hạn trang, ảnh và thời gian OCR."""
    max_pages = current_app.config["MAX_CV_PDF_PAGES"]
    max_pixels = current_app.config["MAX_CV_IMAGE_PIXELS"]
    ocr_timeout = current_app.config["CV_OCR_TIMEOUT"]
    text_parts = []

    with pymupdf.open(file_path) as document:
        if document.needs_pass:
            raise ValueError("PDF có mật khẩu, không thể phân tích.")

        if document.page_count > max_pages:
            raise ValueError(f"CV PDF không được vượt quá {max_pages} trang.")

        for page in document:
            page_text = page.get_text("text").strip()

            if not page_text:
                # Kiểm tra kích thước trước khi tạo ảnh OCR.
                scale = 2
                width = int(page.rect.width * scale + 0.9999)
                height = int(page.rect.height * scale + 0.9999)

                if width * height > max_pixels:
                    raise ValueError("Trang PDF quá lớn để xử lý OCR.")

                pix = page.get_pixmap(
                    matrix=pymupdf.Matrix(scale, scale),
                    colorspace=pymupdf.csRGB,
                    alpha=False
                )

                if pix.width * pix.height > max_pixels:
                    raise ValueError("Trang PDF vượt giới hạn ảnh OCR.")

                image = Image.frombytes(
                    "RGB",
                    (pix.width, pix.height),
                    pix.samples
                )

                try:
                    page_text = pytesseract.image_to_string(
                        image,
                        lang="eng",
                        timeout=ocr_timeout
                    ).strip()
                finally:
                    image.close()

            if page_text:
                text_parts.append(page_text)

    return "\n".join(text_parts).strip()



def extract_docx_text(file_path):
    """Trích xuất text từ file Word DOCX."""

    document = Document(file_path)
    text_parts = []

    # Đọc từng đoạn văn trong tài liệu.
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()

        if text:
            text_parts.append(text)

    return "\n".join(text_parts).strip()


def extract_image_text(file_path):
    """OCR ảnh CV với giới hạn kích thước và thời gian."""
    max_pixels = current_app.config["MAX_CV_IMAGE_PIXELS"]
    ocr_timeout = current_app.config["CV_OCR_TIMEOUT"]

    with Image.open(file_path) as image:
        if image.width * image.height > max_pixels:
            raise ValueError("Ảnh CV vượt giới hạn kích thước.")

        rgb_image = image.convert("RGB")

    try:
        return pytesseract.image_to_string(
            rgb_image,
            lang="eng",
            timeout=ocr_timeout
        ).strip()
    finally:
        rgb_image.close()


def extract_cv_text(cv):
    """Chọn phương pháp trích xuất theo định dạng CV."""

    if cv.file_type == "PDF":
        return extract_pdf_text(cv.file_path)

    if cv.file_type == "DOCX":
        return extract_docx_text(cv.file_path)

    if cv.file_type in {"JPG", "JPEG", "PNG"}:
        return extract_image_text(cv.file_path)

    return ""


def save_extracted_text(cv):
    """Đọc nội dung CV và lưu text vào database."""

    try:
        # Trích xuất nội dung theo định dạng CV.
        extracted_text = extract_cv_text(cv)

        if not extracted_text:
            return False, "Chưa thể đọc được nội dung CV này."

        # Lưu nội dung CV vào MySQL.
        cv.extracted_text = extracted_text

        db.session.commit()

        return True, extracted_text

    except Exception:
        # Hoàn tác nếu đọc file hoặc lưu database thất bại.
        db.session.rollback()

        return False, "Không thể đọc nội dung CV. Vui lòng thử lại."


def upload_cv(user_id, file):
    """Kiểm tra, lưu file CV và tạo bản ghi trong database."""

    if file is None or not file.filename:
        return False, "Vui lòng chọn CV để tải lên."

    # Làm an toàn tên file.
    original_filename = secure_filename(file.filename)

    if not original_filename or "." not in original_filename:
        return False, "File CV không hợp lệ."

    # Lấy phần mở rộng của file.
    extension = original_filename.rsplit(".", 1)[1].lower()

    if extension not in ALLOWED_CV_EXTENSIONS:
        return (
            False,
            "JobFit chỉ hỗ trợ CV định dạng PDF, DOCX, JPG, JPEG hoặc PNG."
        )

    # Kiểm tra nội dung thật của file.
    if not is_valid_cv_content(file, extension):
        return (
            False,
            "Nội dung file không đúng với định dạng PDF, DOCX, JPG, JPEG hoặc PNG."
        )

    # Tạo tên riêng để tránh trùng file.
    stored_filename = f"{uuid.uuid4().hex}.{extension}"

    upload_folder = current_app.config["UPLOAD_CV_FOLDER"]

    # Tạo thư mục nếu chưa tồn tại.
    os.makedirs(upload_folder, exist_ok=True)

    file_path = os.path.join(upload_folder, stored_filename)

    try:
        # Lưu file CV vào server.
        file.save(file_path)

        # Tạo bản ghi CV trong MySQL.
        cv = CV(
            user_id=user_id,
            file_name=original_filename,
            file_path=file_path,
            file_type=extension.upper(),
            analysis_status="PENDING"
        )

        db.session.add(cv)
        db.session.commit()

        return True, cv

    except Exception:
        db.session.rollback()

        # Xóa file nếu lưu database thất bại.
        if os.path.exists(file_path):
            os.remove(file_path)

        return False, "Không thể tải CV lên. Vui lòng thử lại."


def delete_cv(user_id, cv_id):
    """Xóa CV thuộc đúng Candidate đang đăng nhập."""
    linked_message = (
        "Không thể xóa CV vì đã được sử dụng trong đơn ứng tuyển, kể cả đơn đã rút. "
        "CV và lịch sử ứng tuyển phải được giữ nguyên."
    )
    try:
        user = User.query.filter_by(user_id=user_id).populate_existing().with_for_update().first()
        if user is None or user.role != "CANDIDATE" or user.user_status != "ACTIVE":
            db.session.rollback()
            return False, "Chỉ Candidate đang hoạt động được xóa CV."
        # Dùng cùng khóa CV với luồng nộp đơn, bảo toàn cả file khi có tham chiếu.
        cv = CV.query.filter_by(cv_id=cv_id, user_id=user_id).populate_existing().with_for_update().first()
        if cv is None:
            db.session.rollback()
            return False, "Không tìm thấy CV hoặc bạn không có quyền xóa CV này."
        if Application.query.filter_by(cv_id=cv_id).with_for_update().first() is not None:
            db.session.rollback()
            return False, linked_message
        file_path = cv.file_path
        # Chỉ xóa kỹ năng của CV không có đơn, trong cùng transaction xóa CV.
        CandidateSkill.query.filter_by(cv_id=cv_id).delete(synchronize_session=False)
        db.session.delete(cv)
        db.session.commit()

        # Xóa file thật sau khi database đã cập nhật.
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

        return True, "Xóa CV thành công."

    except IntegrityError:
        db.session.rollback()
        return False, "Không thể xóa CV đang được tham chiếu. CV và lịch sử liên quan được giữ nguyên."
    except Exception:
        db.session.rollback()

        return False, "Không thể xóa CV. Vui lòng thử lại."
