#	Nộp đơn, xem hồ sơ, chuyển trạng thái, rút đơn, thay CV và kiểm tra quyền.
import re
from datetime import date, datetime
from types import SimpleNamespace

from flask import current_app
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.application import Application
from app.models.company import Company
from app.models.cv import CV
from app.models.job import Job
from app.models.user import User
from app.services.cv_service import get_selectable_user_cvs
from app.services.notification_service import lock_event_users, add_notification
from app.services.job_service import visible_jobs, job_availability


DUPLICATE_MESSAGE = "Bạn đã ứng tuyển công việc này. Đơn đã rút vẫn được tính là đã ứng tuyển."
SAVE_ERROR = "Không thể lưu đơn ứng tuyển. Vui lòng thử lại."
APPLICATION_STATES = ("SUBMITTED", "VIEWED", "CONSIDERING", "INTERVIEW", "REJECTED", "WITHDRAWN")
WITHDRAWABLE_STATES = frozenset({"SUBMITTED", "VIEWED", "CONSIDERING", "INTERVIEW"})


def _recruiter_applications_query(user_id):
    # Chỉ chọn trường cần cho danh sách, không tải trước CV hoặc thư giới thiệu.
    return db.session.query(
        Application.application_id, Application.user_id, Application.contact_name,
        Application.application_status, Application.applied_at, Application.withdrawn_at,
        Job.job_id, Job.job_title, Job.job_status, Job.is_hidden, Job.application_deadline,
    ).select_from(Application).join(Job, Job.job_id == Application.job_id).join(
        Company, Company.company_id == Job.company_id
    ).join(User, User.user_id == Company.user_id).filter(
        User.user_id == user_id, User.role == "RECRUITER", User.user_status == "ACTIVE"
    )


def _recruiter_application_data(row):
    return SimpleNamespace(
        application_id=row.application_id, contact_name=row.contact_name,
        application_status=row.application_status, applied_at=row.applied_at,
        withdrawn_at=row.withdrawn_at, job_id=row.job_id, job_title=row.job_title,
        job_status="HIDDEN" if row.is_hidden else job_availability(row),
        is_hidden=bool(row.is_hidden), is_submitted=row.application_status == "SUBMITTED",
        can_consider=not row.is_hidden and row.application_status == "VIEWED",
        can_reject=not row.is_hidden and row.application_status in {"VIEWED", "CONSIDERING"},
    )


def get_recruiter_applications(user_id, page=1, job_id="", status="", keyword=""):
    jobs = db.session.query(Job.job_id, Job.job_title).join(Company).join(
        User, User.user_id == Company.user_id
    ).filter(User.user_id == user_id, User.role == "RECRUITER", User.user_status == "ACTIVE").order_by(
        Job.job_created_at.desc(), Job.job_id.desc()
    ).all()
    selected_job = None
    if job_id not in (None, ""):
        selected_job = _parse_cv_id(job_id)
        if selected_job is None or selected_job not in {job.job_id for job in jobs}:
            return None
    status = status if status in APPLICATION_STATES else ""
    keyword = keyword.strip()[:150]
    query = _recruiter_applications_query(user_id)
    if selected_job:
        query = query.filter(Application.job_id == selected_job)
    if status:
        query = query.filter(Application.application_status == status)
    if keyword:
        pattern = "%" + keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.filter(or_(*(column.ilike(pattern, escape="\\") for column in (
            Application.contact_name, Application.contact_email, Application.contact_phone
        ))))
    query = query.order_by(Application.applied_at.desc(), Application.application_id.desc())
    pagination = query.paginate(page=max(1, min(page, 2147483647)), per_page=10, error_out=False)
    if pagination.total and not pagination.items and pagination.page > pagination.pages:
        pagination = query.paginate(page=pagination.pages, per_page=10, error_out=False)
    return {"applications": [_recruiter_application_data(row) for row in pagination.items],
            "pagination": pagination, "jobs": jobs, "selected_job": selected_job,
            "selected_status": status, "keyword": keyword}


def get_recruiter_application_detail(user_id, application_id):
    row = _recruiter_applications_query(user_id).filter(Application.application_id == application_id).first()
    if row is None:
        return None
    result = _recruiter_application_data(row)
    if not result.is_submitted:
        # GET không thay trạng thái. Đơn SUBMITTED chỉ trả dữ liệu chờ mở.
        details = db.session.query(Application.contact_email, Application.contact_phone,
                                   Application.cover_letter, Application.cv_id).filter_by(
            application_id=application_id, user_id=row.user_id
        ).first()
        cv = CV.query.filter_by(cv_id=details.cv_id, user_id=row.user_id).first()
        result.contact_email, result.contact_phone = details.contact_email, details.contact_phone
        result.cover_letter = details.cover_letter
        result.cv_name = cv.file_name if cv else None
    return result


def _candidate_applications_query(user_id):
    return db.session.query(Application, Job, Company).select_from(Application).join(
        User, User.user_id == Application.user_id
    ).outerjoin(Job, Job.job_id == Application.job_id).outerjoin(
        Company, Company.company_id == Job.company_id
    ).filter(Application.user_id == user_id, User.role == "CANDIDATE", User.user_status == "ACTIVE")


def _candidate_application_data(application, job, company):
    # Không đưa tên công ty, Job hoặc JD bị ẩn vào dữ liệu truyền cho View.
    availability = job_availability(job)
    available = availability != "UNAVAILABLE"
    return SimpleNamespace(
        application_id=application.application_id, applied_at=application.applied_at,
        application_status=application.application_status, withdrawn_at=application.withdrawn_at,
        job_status=availability, job_id=job.job_id if availability == "OPEN" else None,
        job_title=job.job_title if available else "Tin tuyển dụng hiện không còn khả dụng.",
        company_name=company.company_name if available and company else "",
        can_replace=application.application_status == "SUBMITTED",
        can_withdraw=application.application_status in WITHDRAWABLE_STATES,
    )


def get_candidate_applications(user_id, page=1, status=""):
    status = status if status in APPLICATION_STATES else ""
    query = _candidate_applications_query(user_id)
    if status:
        query = query.filter(Application.application_status == status)
    pagination = query.order_by(Application.applied_at.desc(), Application.application_id.desc()).paginate(
        page=max(1, min(page, 2147483647)), per_page=10, error_out=False
    )
    if pagination.total and not pagination.items and pagination.page > pagination.pages:
        pagination = query.order_by(Application.applied_at.desc(), Application.application_id.desc()).paginate(
            page=pagination.pages, per_page=10, error_out=False
        )
    return [_candidate_application_data(*row) for row in pagination.items], pagination, status


def get_candidate_application_detail(user_id, application_id):
    row = _candidate_applications_query(user_id).filter(Application.application_id == application_id).first()
    if row is None:
        return None
    application, job, company = row
    result = _candidate_application_data(*row)
    cv = CV.query.filter_by(cv_id=application.cv_id, user_id=user_id).first()
    result.cv = {"id": cv.cv_id, "name": cv.file_name, "type": cv.file_type} if cv else None
    result.contact_name = application.contact_name
    result.contact_email = application.contact_email
    result.contact_phone = application.contact_phone
    result.cover_letter = application.cover_letter
    result.selectable_cvs = get_selectable_user_cvs(user_id) if result.can_replace else []
    return result


def get_application_statuses(user_id, job_ids):
    """Mọi đơn trong lịch sử đều chặn nộp lại, kể cả WITHDRAWN."""
    if not job_ids:
        return {}
    return {row.job_id: row.application_status or "UNKNOWN" for row in db.session.query(
        Application.job_id, Application.application_status
    ).filter(
        Application.user_id == user_id, Application.job_id.in_(job_ids)
    ).all()}


def get_application_options(user_id, job_id):
    """Chỉ chuẩn bị form, không thay đổi Application hoặc trạng thái CV."""
    user = User.query.filter_by(user_id=user_id, role="CANDIDATE", user_status="ACTIVE").first()
    if user is None:
        return None, {"account": "Chỉ Candidate đang hoạt động được ứng tuyển."}
    job = visible_jobs().filter(Job.job_id == job_id).first()
    if job is None:
        return None, {"job": "Tin tuyển dụng không còn khả dụng hoặc đã hết hạn."}
    company = db.session.get(Company, job.company_id)
    status = get_application_statuses(user_id, [job_id]).get(job_id)
    return {
        "job": {"id": job_id, "title": job.job_title,
                "company": company.company_name if company else "Chưa cập nhật công ty"},
        "contact": {"contact_name": user.user_name, "contact_email": user.email,
                    "contact_phone": user.phone or ""},
        "cvs": [{"id": cv.cv_id, "name": cv.file_name} for cv in get_selectable_user_cvs(user_id)],
        "application_status": status,
    }, {}


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
    recent_applications = [
        _candidate_application_data(*row) for row in _candidate_applications_query(user_id)
        .order_by(Application.applied_at.desc(), Application.application_id.desc())
        .limit(5)
        .all()
    ]
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
        recipient_id = db.session.query(Company.user_id).join(Job, Job.company_id == Company.company_id).filter(Job.job_id == job_id).scalar()
        users = lock_event_users(user_id, recipient_id)
        user = users.get(user_id)
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
        locked_job = db.session.query(Job, Company.user_id).join(Company).filter(Job.job_id == job_id).populate_existing().with_for_update().first()
        job = locked_job[0] if locked_job else None
        if locked_job and locked_job[1] != recipient_id:
            db.session.rollback()
            return None, {"application": SAVE_ERROR}
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
        db.session.flush()
        add_notification(recipient_id, "APP_SUBMITTED", f"application:{application.application_id}:submitted",
                         application_id=application.application_id, job_id=job.job_id)
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


def withdraw_application(user_id, application_id):
    """Rút đơn dưới khóa User → CV → Application, không phụ thuộc trạng thái Job."""
    try:
        for _ in range(3):
            hint = db.session.query(Application.cv_id, Application.job_id, Company.user_id.label("recipient_id")).join(Job, Job.job_id == Application.job_id).join(Company, Company.company_id == Job.company_id).filter(Application.application_id == application_id, Application.user_id == user_id).first()
            users = lock_event_users(user_id, hint.recipient_id if hint else None)
            user = users.get(user_id)
            if user is None or user.role != "CANDIDATE" or user.user_status != "ACTIVE":
                return _application_error("account", "Chỉ Candidate đang hoạt động được rút đơn.")
            reference = db.session.query(Application.cv_id).filter_by(
                application_id=application_id, user_id=user_id
            ).first()
            if reference is None:
                return _application_error("application", "Không tìm thấy đơn hoặc bạn không có quyền truy cập.")
            cvs = _lock_owned_cvs(user_id, [reference.cv_id])
            locked_job = db.session.query(Job, Company.user_id).join(Company).filter(Job.job_id == hint.job_id).populate_existing().with_for_update().first()
            if locked_job is None or locked_job[1] != hint.recipient_id:
                return _application_error("concurrency", "Hồ sơ vừa thay đổi. Vui lòng tải lại.")
            application = Application.query.filter_by(
                application_id=application_id, user_id=user_id
            ).populate_existing().with_for_update().first()
            if application is None:
                return _application_error("application", "Không tìm thấy đơn hoặc bạn không có quyền truy cập.")
            if application.cv_id != reference.cv_id:
                db.session.rollback()
                continue
            if reference.cv_id not in cvs:
                return _application_error("cv", "Không tìm thấy CV thuộc hồ sơ của bạn.")
            if application.application_status == "WITHDRAWN":
                result = {"application_id": application.application_id, "application_status": "WITHDRAWN"}
                db.session.rollback()
                return result, {}
            if application.application_status not in WITHDRAWABLE_STATES:
                return _application_error("state", "Không thể rút đơn ở trạng thái hiện tại.")
            application.application_status = "WITHDRAWN"
            application.withdrawn_at = datetime.utcnow()
            result = {"application_id": application.application_id, "application_status": "WITHDRAWN"}
            add_notification(hint.recipient_id, "APP_WITHDRAWN", f"application:{application.application_id}:withdrawn",
                             application_id=application.application_id, job_id=application.job_id)
            db.session.commit()
            return result, {}
        return _application_error("concurrency", "Hồ sơ vừa thay đổi. Vui lòng tải lại và thử lại.")
    except SQLAlchemyError as error:
        current_app.logger.error("Không thể rút Application (%s).", type(error).__name__)
        return _application_error("database", "Không thể rút đơn lúc này. Vui lòng thử lại.")


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


def _lock_recruiter_application(user_id, application_id):
    """Khóa User → CV → Job → Application, đọc lại quyền sở hữu và CV mới nhất."""
    for _ in range(3):
        reference = db.session.query(Application.cv_id, Application.job_id, Application.user_id).join(
            Job, Job.job_id == Application.job_id
        ).join(Company, Company.company_id == Job.company_id).filter(
            Application.application_id == application_id, Company.user_id == user_id
        ).first()
        users = lock_event_users(user_id, reference.user_id if reference else None)
        user = users.get(user_id)
        if user is None or user.role != "RECRUITER" or user.user_status != "ACTIVE":
            return _application_error("account", "Chỉ Recruiter đang hoạt động được xem hồ sơ.")
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
        return (application, job, cv), {}
    return _application_error("concurrency", "Hồ sơ vừa thay đổi. Vui lòng mở lại.")


def open_recruiter_application(user_id, application_id, with_cv=False):
    """Mở hồ sơ thuộc công ty, chỉ chuyển SUBMITTED thành VIEWED."""
    cv_file = None
    try:
        locked, errors = _lock_recruiter_application(user_id, application_id)
        if errors:
            return None, errors
        application, job, cv = locked
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
            add_notification(application.user_id, "APP_VIEWED", f"application:{application.application_id}:viewed",
                             application_id=application.application_id, job_id=application.job_id)
            db.session.commit()
        else:
            db.session.rollback()
        if with_cv:
            result.update(cv_file=cv_file, file_type=file_type)
        return result, {}
    except OSError:
        if cv_file is not None:
            cv_file.close()
        return _application_error("cv", "Không thể mở file CV đã nộp.")
    except SQLAlchemyError as error:
        if cv_file is not None:
            cv_file.close()
        current_app.logger.error("Không thể mở Application (%s).", type(error).__name__)
        return _application_error("database", "Không thể mở hồ sơ lúc này. Vui lòng thử lại.")


def transition_recruiter_application_status(user_id, application_id, target_status):
    """Chỉ xét tuyển dưới khóa, không cho tiếp tục xử lý tin bị Admin ẩn."""
    if target_status not in {"CONSIDERING", "REJECTED"}:
        return _application_error("state", "Trạng thái đích không hợp lệ.")
    try:
        locked, errors = _lock_recruiter_application(user_id, application_id)
        if errors:
            return None, errors
        application, job, cv = locked
        if job.is_hidden:
            return _application_error("job", "Tin đã bị Admin ẩn. Bạn chỉ được xem lịch sử hồ sơ.")
        if job.job_status not in {"OPEN", "CLOSED", "EXPIRED"}:
            return _application_error("job", "Tin tuyển dụng có trạng thái không hợp lệ.")
        current = application.application_status
        if current == target_status:
            result = {"application_id": application.application_id, "application_status": current}
            db.session.rollback()
            return result, {}
        allowed = {"VIEWED": {"CONSIDERING", "REJECTED"}, "CONSIDERING": {"REJECTED"}}
        if target_status not in allowed.get(current, set()):
            return _application_error("state", "Không thể chuyển trạng thái hồ sơ. Vui lòng tải lại để xem trạng thái mới nhất.")
        application.application_status = target_status
        result = {"application_id": application.application_id, "application_status": target_status}
        add_notification(application.user_id, "APP_" + target_status,
                         f"application:{application.application_id}:{target_status.lower()}",
                         application_id=application.application_id, job_id=application.job_id)
        db.session.commit()
        return result, {}
    except SQLAlchemyError as error:
        current_app.logger.error("Không thể xử lý Application (%s).", type(error).__name__)
        return _application_error("database", "Không thể cập nhật hồ sơ. Vui lòng thử lại.")
