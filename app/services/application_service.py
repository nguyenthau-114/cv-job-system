"""Kiểm tra và lưu đơn ứng tuyển, không thay đổi tài khoản hoặc phân tích CV."""
import re
from datetime import date

from flask import current_app
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.application import Application
from app.models.company import Company
from app.models.cv import CV
from app.models.job import Job
from app.models.user import User


DUPLICATE_MESSAGE = "Bạn đã ứng tuyển công việc này. Đơn đã rút vẫn được tính là đã ứng tuyển."
SAVE_ERROR = "Không thể lưu đơn ứng tuyển. Vui lòng thử lại."


def get_candidate_dashboard(user_id):
    """Đọc thống kê và năm đơn gần nhất, không thay đổi CV hoặc Application."""
    # Đếm theo chủ CV và chủ đơn riêng biệt, không suy ra chủ đơn qua CV.
    cv_count = CV.query.filter_by(user_id=user_id).count()
    status_counts = dict(
        db.session.query(Application.application_status, func.count(Application.application_id))
        .filter(Application.user_id == user_id)
        .group_by(Application.application_status)
        .all()
    )
    statistics = {
        "cvs": cv_count,
        "applications": sum(status_counts.values()),
        "reviewing": sum(status_counts.get(status, 0) for status in (
            "SUBMITTED", "VIEWED", "CONSIDERING", "INTERVIEW"
        )),
        "viewed": status_counts.get("VIEWED", 0),
    }
    recent_applications = (
        db.session.query(
            Application.application_id, Application.applied_at, Application.application_status,
            Job.job_title, Company.company_name,
        )
        .select_from(Application)
        .join(Job, Job.job_id == Application.job_id)
        .join(Company, Company.company_id == Job.company_id)
        .filter(Application.user_id == user_id)
        .order_by(Application.applied_at.desc(), Application.application_id.desc())
        .limit(5)
        .all()
    )
    return {"statistics": statistics, "recent_applications": recent_applications}


def _parse_cv_id(value):
    if type(value) is int:
        return value if 1 <= value <= 2147483647 else None
    if not isinstance(value, str):
        return None
    value = value.strip()
    try:
        if value.isascii() and value.isdecimal() and 1 <= int(value) <= 2147483647:
            return int(value)
    except ValueError:
        pass
    return None


def validate_application_form(form):
    """Chỉ đọc CV đã lưu và thông tin liên hệ riêng của đơn."""
    fields = ("cv_id", "contact_name", "contact_email", "contact_phone", "cover_letter")
    data, errors = {}, {}
    for field in fields:
        value = form.get(field, "")
        if not isinstance(value, str):
            errors[field] = "Dữ liệu không hợp lệ."
            value = ""
        if hasattr(form, "getlist") and len(form.getlist(field)) > 1:
            errors[field] = "Mỗi trường chỉ được gửi một giá trị."
        data[field] = value.strip()

    data["cv_id"] = _parse_cv_id(data["cv_id"])
    if data["cv_id"] is None:
        errors["cv_id"] = "Vui lòng chọn CV đã lưu trong tài khoản tại trang Quản lý CV."

    for field, label in (
        ("contact_name", "Họ tên"),
        ("contact_email", "Email"),
        ("contact_phone", "Số điện thoại"),
    ):
        limit = Application.__table__.c[field].type.length
        if not data[field] or len(data[field]) > limit or "\x00" in data[field]:
            errors[field] = f"{label} bắt buộc và không được vượt quá {limit} ký tự."
    if data["contact_email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", data["contact_email"]):
        errors["contact_email"] = "Email không đúng định dạng."
    if data["contact_phone"] and not re.fullmatch(r"\+?[0-9][0-9 ()-]*", data["contact_phone"]):
        errors["contact_phone"] = "Số điện thoại không hợp lệ."
    if len(data["cover_letter"]) > 5000 or "\x00" in data["cover_letter"]:
        errors["cover_letter"] = "Thư giới thiệu không được vượt quá 5.000 ký tự và phải là văn bản hợp lệ."
    data["cover_letter"] = data["cover_letter"] or None
    return data, errors


def submit_application(user_id, job_id, form):
    """Trả về (Application, errors). user_id phải do Controller lấy từ session."""
    data, errors = validate_application_form(form)
    if errors:
        return None, errors

    try:
        # Đọc lại tài khoản/CV dưới khóa, không tin role hoặc ownership từ client.
        user = User.query.filter_by(user_id=user_id).populate_existing().with_for_update().first()
        if user is None or user.role != "CANDIDATE" or user.user_status != "ACTIVE":
            db.session.rollback()
            return None, {"account": "Chỉ Candidate đang hoạt động được ứng tuyển."}
        cv = CV.query.filter_by(
            cv_id=data["cv_id"], user_id=user.user_id
        ).populate_existing().with_for_update().first()
        if cv is None or cv.is_hidden:
            db.session.rollback()
            return None, {"cv_id": "Vui lòng chọn CV thuộc tài khoản và đang hiển thị tại trang Quản lý CV."}

        # Cùng khóa Job với luồng Recruiter sửa/đóng tin, kiểm tra ngay trước khi lưu.
        job = Job.query.filter_by(job_id=job_id).populate_existing().with_for_update().first()
        if (
            job is None or job.job_status != "OPEN" or job.is_hidden
            or job.application_deadline is None or job.application_deadline < date.today()
        ):
            db.session.rollback()
            return None, {"job": "Tin không tồn tại hoặc không còn nhận đơn ứng tuyển."}
        duplicate = Application.query.filter_by(
            user_id=user.user_id, job_id=job.job_id
        ).with_for_update().first()
        if duplicate is not None:
            db.session.rollback()
            return None, {"application": DUPLICATE_MESSAGE}

        # Không kiểm tra analysis_status, không thay quantity hoặc thông tin User.
        application = Application(
            user_id=user.user_id, cv_id=cv.cv_id, job_id=job.job_id,
            contact_name=data["contact_name"], contact_email=data["contact_email"],
            contact_phone=data["contact_phone"], cover_letter=data["cover_letter"],
            application_status="SUBMITTED",
        )
        db.session.add(application)
        db.session.commit()
        return application, {}
    except IntegrityError:
        # UNIQUE là lớp bảo vệ cuối cùng khi có request đồng thời hoặc nguồn ghi khác.
        db.session.rollback()
        try:
            duplicate = Application.query.filter_by(user_id=user_id, job_id=job_id).first()
            is_duplicate = duplicate is not None
        except SQLAlchemyError:
            is_duplicate = False
        finally:
            db.session.rollback()
        return None, {"application": DUPLICATE_MESSAGE if is_duplicate else SAVE_ERROR}
    except SQLAlchemyError as error:
        db.session.rollback()
        # Không ghi câu SQL hoặc thông tin liên hệ cá nhân vào log lỗi.
        current_app.logger.error("Không thể lưu Application (%s).", type(error).__name__)
        return None, {"application": SAVE_ERROR}


def _application_error(field, message):
    db.session.rollback()
    return None, {field: message}


def _lock_owned_cvs(user_id, cv_ids):
    """Khóa từng CV theo ID tăng dần, luôn trước khi khóa Application."""
    locked = {}
    for cv_id in sorted(set(cv_ids)):
        cv = CV.query.filter_by(cv_id=cv_id, user_id=user_id).populate_existing().with_for_update().first()
        if cv is not None:
            locked[cv_id] = cv
    return locked


def replace_application_cv(user_id, application_id, cv_id):
    """Chỉ đổi CV của đơn SUBMITTED, không kiểm tra trạng thái Job."""
    cv_id = _parse_cv_id(cv_id)
    if cv_id is None:
        return _application_error("cv_id", "Vui lòng chọn CV đã lưu hợp lệ.")
    try:
        for _ in range(3):
            user = User.query.filter_by(user_id=user_id).populate_existing().with_for_update().first()
            if user is None or user.role != "CANDIDATE" or user.user_status != "ACTIVE":
                return _application_error("account", "Chỉ Candidate đang hoạt động được thay CV.")
            reference = db.session.query(Application.cv_id).filter(
                Application.application_id == application_id, Application.user_id == user_id
            ).first()
            if reference is None:
                return _application_error("application", "Không tìm thấy đơn hoặc bạn không có quyền truy cập.")
            cvs = _lock_owned_cvs(user_id, [reference.cv_id, cv_id])
            application = Application.query.filter_by(
                application_id=application_id, user_id=user_id
            ).populate_existing().with_for_update().first()
            if application is None:
                return _application_error("application", "Không tìm thấy đơn hoặc bạn không có quyền truy cập.")
            # Hint không khóa có thể cũ do isolation hoặc request vừa hoàn tất.
            if application.cv_id != reference.cv_id:
                db.session.rollback()
                continue
            if application.application_status != "SUBMITTED":
                return _application_error("state", "Chỉ được thay CV khi hồ sơ còn SUBMITTED và Recruiter chưa xem.")
            cv = cvs.get(cv_id)
            if cv is None or cv.is_hidden:
                return _application_error("cv_id", "CV thay thế phải thuộc tài khoản của bạn và không bị ẩn.")
            result = {"application_id": application.application_id, "cv_id": cv.cv_id}
            if application.cv_id == cv.cv_id:
                db.session.rollback()
                return result, {}
            application.cv_id = cv.cv_id
            db.session.commit()
            return result, {}
        return _application_error("concurrency", "Hồ sơ vừa thay đổi. Vui lòng tải lại và thử lại.")
    except SQLAlchemyError as error:
        current_app.logger.error("Không thể thay CV trong Application (%s).", type(error).__name__)
        return _application_error("database", "Không thể thay CV lúc này. Vui lòng thử lại.")


def open_recruiter_application(user_id, application_id, with_cv=False):
    """Mở hồ sơ thuộc công ty, đánh dấu VIEWED trước khi trả nội dung."""
    cv_file = None
    try:
        for _ in range(3):
            user = User.query.filter_by(user_id=user_id).populate_existing().with_for_update().first()
            if user is None or user.role != "RECRUITER" or user.user_status != "ACTIVE":
                return _application_error("account", "Chỉ Recruiter đang hoạt động được xem hồ sơ.")
            reference = db.session.query(Application.cv_id, Application.job_id, Application.user_id).join(
                Job, Job.job_id == Application.job_id
            ).join(Company, Company.company_id == Job.company_id).filter(
                Application.application_id == application_id, Company.user_id == user_id
            ).first()
            if reference is None:
                return _application_error("application", "Không tìm thấy hồ sơ hoặc bạn không có quyền truy cập.")
            cvs = _lock_owned_cvs(reference.user_id, [reference.cv_id])
            job = Job.query.join(Company, Company.company_id == Job.company_id).filter(
                Job.job_id == reference.job_id, Company.user_id == user_id
            ).populate_existing().with_for_update().first()
            if job is None:
                return _application_error("application", "Không tìm thấy hồ sơ hoặc bạn không có quyền truy cập.")
            application = Application.query.filter_by(
                application_id=application_id, job_id=job.job_id
            ).populate_existing().with_for_update().first()
            if application is None:
                return _application_error("application", "Không tìm thấy hồ sơ hoặc bạn không có quyền truy cập.")
            if application.cv_id != reference.cv_id or application.user_id != reference.user_id:
                db.session.rollback()
                continue
            cv = cvs.get(application.cv_id)
            if cv is None:
                return _application_error("cv", "Không tìm thấy CV đã nộp.")
            # Không lọc is_hidden. Mở file dưới khóa để giữ đúng CV ngay cả khi có xóa đồng thời.
            if with_cv:
                cv_file = open(cv.file_path, "rb")
                file_type = cv.file_type
            if application.application_status == "SUBMITTED":
                application.application_status = "VIEWED"
                changed = True
            else:
                changed = False
            result = {
                "application_id": application.application_id, "job_id": application.job_id,
                "cv_id": cv.cv_id, "cv_name": cv.file_name,
                "applied_at": application.applied_at.isoformat(),
                "contact_name": application.contact_name, "contact_email": application.contact_email,
                "contact_phone": application.contact_phone, "cover_letter": application.cover_letter,
                "application_status": application.application_status,
            }
            if changed:
                db.session.commit()
            else:
                db.session.rollback()
            if with_cv:
                result.update(cv_file=cv_file, file_type=file_type)
            return result, {}
        return _application_error("concurrency", "Hồ sơ vừa thay đổi. Vui lòng mở lại.")
    except OSError:
        if cv_file is not None:
            cv_file.close()
        return _application_error("cv", "Không thể mở file CV đã nộp.")
    except SQLAlchemyError as error:
        if cv_file is not None:
            cv_file.close()
        current_app.logger.error("Không thể mở Application (%s).", type(error).__name__)
        return _application_error("database", "Không thể mở hồ sơ lúc này. Vui lòng thử lại.")
