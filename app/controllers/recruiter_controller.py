import json
import os
import secrets
import time
from datetime import date, datetime
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for, abort, jsonify, send_file
from app.extensions import db
from app.middleware.auth_middleware import role_required
from app.models.company import Company
from app.models.job import Job
from app.models.job_category import JobCategory
from app.models.skill import Skill
from app.services.job_service import validate_job_form, extract_job_skills, publish_job
from app.models.job_skill import JobSkill
from decimal import Decimal, InvalidOperation
from app.models.application import Application
from io import BytesIO
from PIL import Image, UnidentifiedImageError
from app.models.user import User
from app.services.auth_service import validate_password
from app.services.application_service import open_recruiter_application
from urllib.parse import urlsplit
from werkzeug.exceptions import HTTPException

recruiter_bp = Blueprint("recruiter", __name__, url_prefix="/recruiter")
PENDING_JOB_TTL = 1800


def _open_application_response(application_id, with_cv=False):
    # POST có CSRF: tải trước URL không được tự đánh dấu hồ sơ đã xem.
    if (
        request.files or set(request.form) - {"csrf_token"}
        or any(len(request.form.getlist(key)) != 1 for key in request.form)
    ):
        return jsonify(success=False, errors={"application": "Yêu cầu xem hồ sơ không hợp lệ."}), 400
    result, errors = open_recruiter_application(session["user_id"], application_id, with_cv=with_cv)
    if errors:
        statuses = {"account": 403, "application": 404, "cv": 404, "concurrency": 409, "database": 503}
        return jsonify(success=False, errors=errors), statuses.get(next(iter(errors)), 400)
    if with_cv:
        cv_file = result["cv_file"]
        mimetypes = {
            "PDF": "application/pdf", "DOCX": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "JPG": "image/jpeg", "JPEG": "image/jpeg", "PNG": "image/png",
        }
        try:
            response = send_file(
                cv_file, download_name=result["cv_name"], as_attachment=False,
                mimetype=mimetypes.get(result["file_type"], "application/octet-stream"),
            )
        except (OSError, ValueError):
            cv_file.close()
            return jsonify(success=False, errors={"cv": "Không thể gửi file CV đã nộp."}), 503
        response.call_on_close(cv_file.close)
        response.headers["X-Content-Type-Options"] = "nosniff"
    else:
        response = jsonify(success=True, application=result)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@recruiter_bp.route("/applications/<int:application_id>/open", methods=["POST"])
@role_required("RECRUITER")
def open_application(application_id):
    return _open_application_response(application_id)


@recruiter_bp.route("/applications/<int:application_id>/cv", methods=["POST"])
@role_required("RECRUITER")
def open_application_cv(application_id):
    return _open_application_response(application_id, with_cv=True)


def get_recruiter_company():
    """Lấy công ty của Recruiter đang đăng nhập."""
    return Company.query.filter_by(user_id=session.get("user_id")).first()


def get_active_skills():
    return Skill.query.filter_by(skill_status="ACTIVE").order_by(Skill.skill_name.asc()).all()


def get_job_categories():
    return JobCategory.query.order_by(JobCategory.category_name.asc()).all()


def validate_job_category(data, errors):
    """Kiểm tra danh mục công việc có tồn tại."""
    category = None
    try:
        category_id = int(data.get("job_category_id") or 0)
        category = db.session.get(JobCategory, category_id)
    except (ValueError, TypeError):
        pass
    if category is None:
        errors["job_category_id"] = "Danh mục công việc không hợp lệ."
    return category


def validate_selected_job_skills(form):
    """Kiểm tra danh sách kỹ năng do Recruiter chọn."""
    selected = []
    errors = []
    seen_ids = set()

    for item in form.getlist("selected_skills"):
        try:
            skill_id_text, requirement_type = item.split(":", 1)
            skill_id = int(skill_id_text)
        except (ValueError, TypeError, AttributeError):
            errors.append("Dữ liệu kỹ năng không hợp lệ.")
            continue

        if requirement_type not in ("REQUIRED", "PREFERRED"):
            errors.append("Mức độ yêu cầu kỹ năng không hợp lệ.")
            continue
        if skill_id in seen_ids:
            errors.append("Danh sách kỹ năng bị trùng lặp.")
            continue

        skill = db.session.get(Skill, skill_id)
        if skill is None or skill.skill_status != "ACTIVE":
            errors.append("Có kỹ năng không tồn tại hoặc đã ngừng hoạt động.")
            continue

        seen_ids.add(skill_id)
        selected.append({
            "skill_id": skill.skill_id,
            "skill_name": skill.skill_name,
            "requirement_type": requirement_type
        })

    if not selected:
        errors.append("Vui lòng chọn ít nhất một kỹ năng chuyên môn.")

    return selected, errors


def get_pending_job_directory():
    """Thư mục bản nháp nằm ngoài thư mục public."""
    folder = Path(current_app.instance_path) / "pending_jobs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def get_pending_job_path(token):
    """Chỉ chấp nhận token gồm 64 ký tự hex."""
    if not isinstance(token, str) or len(token) != 64:
        return None
    try:
        int(token, 16)
    except ValueError:
        return None
    return get_pending_job_directory() / f"{token}.json"


def save_pending_job(company_id, data, selected_skills):
    """Lưu JD tạm trên server và chỉ giữ token trong session."""
    old_token = session.get("pending_job_token")
    old_path = get_pending_job_path(old_token)
    if old_path is not None:
        old_path.unlink(missing_ok=True)

    token = secrets.token_hex(32)
    payload = {
        "company_id": company_id,
        "user_id": session.get("user_id"),
        "created_at": time.time(),
        "data": data,
        "skills": [
            {
                "skill_id": skill["skill_id"],
                "requirement_type": skill["requirement_type"]
            }
            for skill in selected_skills
        ]
    }

    path = get_pending_job_path(token)
    with path.open("x", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False)

    session["pending_job_token"] = token
    return token


def load_pending_job(token, company):
    """Đọc bản nháp và xác minh quyền sở hữu, thời hạn."""
    if not token or not secrets.compare_digest(
        str(token), str(session.get("pending_job_token") or "")
    ):
        return None

    path = get_pending_job_path(token)
    if path is None:
        return None

    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, ValueError, TypeError):
        return None

    if not isinstance(payload, dict):
        return None
    if payload.get("user_id") != session.get("user_id"):
        return None
    if payload.get("company_id") != company.company_id:
        return None
    created_at = payload.get("created_at")
    if type(created_at) not in (int, float):
        return None
    if time.time() - created_at > PENDING_JOB_TTL:
        return None
    if not isinstance(payload.get("data"), dict):
        return None

    return payload


def get_pending_selected_skills(payload):
    """Kiểm tra lại kỹ năng từ bản nháp."""
    items = payload.get("skills", [])
    if not isinstance(items, list):
        return [], ["Danh sách kỹ năng không hợp lệ."]

    selected = []
    errors = []
    seen_ids = set()

    for item in items:
        if not isinstance(item, dict):
            errors.append("Dữ liệu kỹ năng không hợp lệ.")
            continue

        skill_id = item.get("skill_id")
        requirement_type = item.get("requirement_type")
        if type(skill_id) is not int or requirement_type not in ("REQUIRED", "PREFERRED"):
            errors.append("Dữ liệu kỹ năng không hợp lệ.")
            continue
        if skill_id in seen_ids:
            errors.append("Danh sách kỹ năng bị trùng.")
            continue

        skill = db.session.get(Skill, skill_id)
        if skill is None or skill.skill_status != "ACTIVE":
            errors.append("Kỹ năng không còn hợp lệ.")
            continue

        seen_ids.add(skill_id)
        selected.append({
            "skill_id": skill.skill_id,
            "skill_name": skill.skill_name,
            "requirement_type": requirement_type
        })

    if not selected:
        errors.append("Tin tuyển dụng phải có ít nhất một kỹ năng.")

    return selected, errors



@recruiter_bp.route("/")
@role_required("RECRUITER")
def dashboard():
    """Tổng quan hoạt động tuyển dụng của công ty."""
    company = get_recruiter_company()
    if company is None:
        flash("Vui lòng hoàn tất thông tin công ty trước.", "warning")
        return redirect(url_for("home.home"))

    today = date.today()
    jobs = Job.query.filter_by(company_id=company.company_id).order_by(
        Job.job_created_at.desc(), Job.job_id.desc()
    ).all()

    # Dùng cùng một quy tắc trạng thái cho thống kê và giao diện.
    job_items = [
        {"job": job, "status": get_job_display_status(job, today)}
        for job in jobs
    ]

    statistics = {
        "total": len(job_items),
        "open": sum(item["status"] == "OPEN" for item in job_items),
        "closed": sum(item["status"] == "CLOSED" for item in job_items),
        "expired": sum(item["status"] == "EXPIRED" for item in job_items)
    }

    # Cảnh báo tin còn tối đa 7 ngày nhận hồ sơ.
    attention_jobs = sorted(
        [
            item for item in job_items
            if item["status"] == "OPEN"
            and 0 <= (item["job"].application_deadline - today).days <= 7
        ],
        key=lambda item: item["job"].application_deadline
    )[:5]

    return render_template(
        "recruiter/dashboard.html",
        company=company,
        statistics=statistics,
        recent_jobs=job_items[:5],
        attention_jobs=attention_jobs,
        today=today
    )


@recruiter_bp.route("/jobs")
@role_required("RECRUITER")
def my_jobs():
    """Danh sách tin tuyển dụng thuộc công ty đang đăng nhập."""
    company = get_recruiter_company()
    if company is None:
        flash("Không tìm thấy thông tin công ty.", "warning")
        return redirect(url_for("recruiter.dashboard"))

    jobs = Job.query.filter_by(company_id=company.company_id).order_by(
        Job.job_created_at.desc(), Job.job_id.desc()
    ).all()

    today = date.today()
    job_items = [
        {"job": job, "status": get_job_display_status(job, today)}
        for job in jobs
    ]

    return render_template(
        "recruiter/jobs.html",
        company=company,
        job_items=job_items,
        today=today
    )

@recruiter_bp.route("/jobs/create", methods=["GET", "POST"])
@role_required("RECRUITER")
def create_job():
    """Bước 1: Nhập JD và phân tích kỹ năng."""
    company = get_recruiter_company()
    if company is None:
        flash("Vui lòng hoàn tất thông tin công ty trước.", "warning")
        return redirect(url_for("recruiter.dashboard"))

    data = {}
    errors = {}
    detected_skills = []

    if request.method == "POST":
        data, errors = validate_job_form(request.form)
        validate_job_category(data, errors)

        if not errors and request.form.get("edit_jd") != "1":
            detected_skills = extract_job_skills(data)
            return render_template(
                "recruiter/review_job_skills.html",
                company=company,
                data=data,
                detected_skills=detected_skills,
                available_skills=get_active_skills()
            )

    return render_template(
        "recruiter/create_job.html",
        company=company,
        categories=get_job_categories(),
        data=data,
        errors=errors,
        detected_skills=detected_skills,
        analyzed=False
    )


@recruiter_bp.route("/jobs/confirm", methods=["POST"])
@role_required("RECRUITER")
def confirm_job():
    """Bước 3: Kiểm tra JD và kỹ năng trước khi đăng."""
    company = get_recruiter_company()
    if company is None:
        flash("Không tìm thấy thông tin công ty.", "warning")
        return redirect(url_for("recruiter.dashboard"))

    data, errors = validate_job_form(request.form)
    category = validate_job_category(data, errors)
    selected_skills, skill_errors = validate_selected_job_skills(request.form)

    if errors:
        flash("Thông tin JD không hợp lệ, vui lòng kiểm tra lại.", "warning")
        for message in skill_errors:
            flash(message, "warning")
        return render_template(
            "recruiter/create_job.html",
            company=company,
            categories=get_job_categories(),
            data=data,
            errors=errors,
            detected_skills=[],
            analyzed=False
        )

    if skill_errors:
        for message in skill_errors:
            flash(message, "warning")
        return render_template(
            "recruiter/review_job_skills.html",
            company=company,
            data=data,
            detected_skills=selected_skills,
            available_skills=get_active_skills()
        )

    token = save_pending_job(company.company_id, data, selected_skills)
    return render_template(
        "recruiter/confirm_job.html",
        company=company,
        category=category,
        data=data,
        selected_skills=selected_skills,
        publish_token=token
    )


@recruiter_bp.route("/jobs/confirm/back", methods=["POST"])
@role_required("RECRUITER")
def back_to_job_skills():
    """Quay lại bước 2 mà không mất kỹ năng đã chọn."""
    company = get_recruiter_company()
    if company is None:
        return redirect(url_for("recruiter.dashboard"))

    token = request.form.get("publish_token", "")
    payload = load_pending_job(token, company)
    if payload is None:
        flash("Bản nháp đã hết hạn hoặc không hợp lệ.", "warning")
        return redirect(url_for("recruiter.create_job"))

    selected_skills, errors = get_pending_selected_skills(payload)
    for message in errors:
        flash(message, "warning")

    return render_template(
        "recruiter/review_job_skills.html",
        company=company,
        data=payload["data"],
        detected_skills=selected_skills,
        available_skills=get_active_skills()
    )


@recruiter_bp.route("/jobs/publish", methods=["POST"])
@role_required("RECRUITER")
def publish_confirmed_job():
    """Lưu Job và JobSkill khi Recruiter xác nhận đăng tin."""
    company = get_recruiter_company()
    if company is None:
        flash("Không tìm thấy thông tin công ty.", "warning")
        return redirect(url_for("recruiter.dashboard"))

    token = request.form.get("publish_token", "")
    payload = load_pending_job(token, company)
    if payload is None:
        flash("Bản nháp đã hết hạn, không hợp lệ hoặc đã được sử dụng.", "warning")
        return redirect(url_for("recruiter.my_jobs"))

    path = get_pending_job_path(token)
    lock_path = path.with_suffix(".lock")

    try:
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(lock_fd)
    except FileExistsError:
        flash("Tin tuyển dụng đang được xử lý, vui lòng không gửi lại.", "warning")
        return redirect(url_for("recruiter.my_jobs"))
    except OSError:
        flash("Không thể xử lý yêu cầu lúc này.", "danger")
        return redirect(url_for("recruiter.my_jobs"))

    try:
        payload = load_pending_job(token, company)
        if payload is None:
            flash("Bản nháp không còn hợp lệ.", "warning")
            return redirect(url_for("recruiter.my_jobs"))

        data, errors = validate_job_form(payload["data"])
        validate_job_category(data, errors)
        selected_skills, skill_errors = get_pending_selected_skills(payload)

        if errors or skill_errors:
            flash("Dữ liệu JD hoặc kỹ năng không còn hợp lệ. Vui lòng kiểm tra lại.", "warning")
            return render_template(
                "recruiter/review_job_skills.html",
                company=company,
                data=data,
                detected_skills=selected_skills,
                available_skills=get_active_skills()
            )

        publish_job(company.company_id, data, selected_skills)

        path.unlink(missing_ok=True)
        session.pop("pending_job_token", None)
        flash("Đăng tin tuyển dụng thành công!", "success")
        return redirect(url_for("recruiter.my_jobs"))

    except Exception:
        current_app.logger.exception("Không thể đăng tin tuyển dụng")
        flash("Có lỗi khi lưu tin tuyển dụng. Vui lòng thử lại.", "danger")
        return redirect(url_for("recruiter.my_jobs"))

    finally:
        lock_path.unlink(missing_ok=True)


def get_owned_job(job_id, company_id):
    """Chỉ truy vấn tin thuộc công ty hiện tại."""
    return Job.query.filter_by(
        job_id=job_id,
        company_id=company_id
    ).first_or_404()


def get_job_display_status(job, today=None):
    """Xác định trạng thái hiển thị, ưu tiên tin đã đóng trước tin hết hạn."""
    today = today or date.today()
    if job.is_hidden:
        return "HIDDEN"
    if job.job_status == "CLOSED":
        return "CLOSED"
    if job.application_deadline < today or job.job_status == "EXPIRED":
        return "EXPIRED"
    if job.job_status == "OPEN":
        return "OPEN"
    return "UNKNOWN"


@recruiter_bp.route("/jobs/<int:job_id>")
@role_required("RECRUITER")
def job_detail(job_id):
    """Xem chi tiết tin tuyển dụng thuộc công ty."""
    company = get_recruiter_company()
    if company is None:
        abort(404)

    job = get_owned_job(job_id, company.company_id)
    has_applications = db.session.query(Application.application_id).filter(
        Application.job_id == job.job_id
    ).first() is not None
    can_edit = get_job_display_status(job) == "OPEN"
    can_edit_content = can_edit and not has_applications and job.content_edit_count == 0
    editing = can_edit and request.args.get("edit") == "1"
    category = db.session.get(JobCategory, job.job_category_id)

    skill_rows = (
        db.session.query(JobSkill, Skill)
        .join(Skill, JobSkill.skill_id == Skill.skill_id)
        .filter(JobSkill.job_id == job.job_id)
        .order_by(Skill.skill_name.asc())
        .all()
    )

    required_skills = [
        skill.skill_name
        for job_skill, skill in skill_rows
        if job_skill.requirement_type == "REQUIRED"
    ]
    preferred_skills = [
        skill.skill_name
        for job_skill, skill in skill_rows
        if job_skill.requirement_type == "PREFERRED"
    ]

    return render_template(
        "recruiter/job_detail.html",
        company=company,
        job=job,
        category=category,
        required_skills=required_skills,
        preferred_skills=preferred_skills,
        status=get_job_display_status(job),
        has_applications=has_applications,
        can_edit=can_edit,
        can_edit_content=can_edit_content,
        editing=editing,
        today=date.today()
    )


@recruiter_bp.route("/jobs/<int:job_id>/close", methods=["POST"])
@role_required("RECRUITER")
def close_job(job_id):
    """Chỉ đóng tin đang tuyển, chưa hết hạn và không bị Admin ẩn."""
    company = get_recruiter_company()
    if company is None:
        abort(404)

    job = get_owned_job(job_id, company.company_id)
    if get_job_display_status(job) != "OPEN":
        flash("Tin tuyển dụng không ở trạng thái có thể đóng.", "warning")
        return redirect(url_for("recruiter.job_detail", job_id=job_id))

    try:
        updated = (
            Job.query.filter(
                Job.job_id == job_id,
                Job.company_id == company.company_id,
                Job.job_status == "OPEN",
                Job.is_hidden.is_(False),
                Job.application_deadline >= date.today()
            )
            .update({"job_status": "CLOSED"}, synchronize_session=False)
        )
        if updated != 1:
            db.session.rollback()
            flash("Trạng thái tin đã thay đổi hoặc tin đã hết hạn.", "warning")
        else:
            db.session.commit()
            flash("Đã đóng tin tuyển dụng thành công.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Không thể đóng tin tuyển dụng %s", job_id)
        flash("Không thể đóng tin tuyển dụng. Vui lòng thử lại.", "danger")

    return redirect(url_for("recruiter.job_detail", job_id=job_id))


@recruiter_bp.route("/jobs/<int:job_id>/reopen", methods=["POST"])
@role_required("RECRUITER")
def reopen_job(job_id):
    """Chỉ mở lại tin đã đóng, chưa hết hạn và không bị Admin ẩn."""
    company = get_recruiter_company()
    if company is None:
        abort(404)

    job = get_owned_job(job_id, company.company_id)
    if get_job_display_status(job) != "CLOSED":
        flash("Tin này không đủ điều kiện để mở lại.", "warning")
        return redirect(url_for("recruiter.job_detail", job_id=job_id))

        # Tin đã đóng vẫn hiển thị Đã đóng, nhưng không được mở lại khi quá hạn.
    if job.application_deadline < date.today():
        flash("Không thể mở lại tin tuyển dụng vì đã quá hạn ứng tuyển.", "warning")
        return redirect(url_for("recruiter.job_detail", job_id=job_id))

    try:
        updated = (
            Job.query.filter(
                Job.job_id == job_id,
                Job.company_id == company.company_id,
                Job.job_status == "CLOSED",
                Job.is_hidden.is_(False),
                Job.application_deadline >= date.today()
            )
            .update({"job_status": "OPEN"}, synchronize_session=False)
        )
        if updated != 1:
            db.session.rollback()
            flash("Trạng thái tin đã thay đổi hoặc tin đã hết hạn.", "warning")
        else:
            db.session.commit()
            flash("Đã mở lại tin tuyển dụng thành công.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Không thể mở lại tin tuyển dụng %s", job_id)
        flash("Không thể mở lại tin tuyển dụng. Vui lòng thử lại.", "danger")

    return redirect(url_for("recruiter.job_detail", job_id=job_id))

# ================= CHỈNH SỬA TIN TUYỂN DỤNG =================

def normalize_job_edit_text(value):
    """Đồng nhất xuống dòng và khoảng trắng ngoài trước khi so sánh."""
    return (value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def validate_job_edit(form, job, has_applications):
    """Mỗi action chỉ nhận đúng nhóm trường và quyền tương ứng."""
    errors, data = {}, {}
    action = form.get("action")
    action_fields = {
        "edit_content": {"min_salary", "max_salary", "location", "working_time", "benefit"},
        "increase_quantity": {"quantity"},
        "extend_deadline": {"application_deadline"}
    }
    if action not in action_fields:
        return {}, {"action": "Thao tác chỉnh sửa không hợp lệ."}

    fields = action_fields[action]
    # Không nhận bộ đếm, trường action khác hoặc giá trị lặp từ client.
    if (
        set(form) - fields - {"action", "csrf_token"}
        or not fields.issubset(form)
        or any(len(form.getlist(key)) != 1 for key in form)
    ):
        return {}, {"fields": "Dữ liệu không đúng với thao tác đã chọn."}

    if action == "edit_content":
        if has_applications:
            return {}, {"content": "Tin đã từng có ứng viên: chỉ được tăng số lượng và gia hạn."}
        if job.content_edit_count != 0:
            return {}, {"content": "Tin đã hết lượt chỉnh sửa nội dung."}

        location = normalize_job_edit_text(form.get("location"))
        working_time = normalize_job_edit_text(form.get("working_time"))
        benefit = normalize_job_edit_text(form.get("benefit"))
        if not 1 <= len(location) <= 255:
            errors["location"] = "Địa điểm phải có từ 1 đến 255 ký tự."
        if len(working_time) > 255:
            errors["working_time"] = "Thời gian làm việc tối đa 255 ký tự."
        data.update(location=location, working_time=working_time or None, benefit=benefit or None)
        for field in ("min_salary", "max_salary"):
            raw = (form.get(field) or "").strip()
            if not raw:
                data[field] = None
                continue
            try:
                amount = Decimal(raw)
                if not amount.is_finite() or amount < 0 or amount > Decimal("9999999999999.99"):
                    raise InvalidOperation
                if amount != amount.quantize(Decimal("0.01")):
                    raise InvalidOperation
                data[field] = amount
            except (InvalidOperation, ValueError):
                errors[field] = "Mức lương không hợp lệ."
        minimum, maximum = data.get("min_salary"), data.get("max_salary")
        if minimum is not None and maximum is not None and minimum > maximum:
            errors["max_salary"] = "Lương tối đa phải lớn hơn hoặc bằng lương tối thiểu."
    elif action == "increase_quantity":
        raw_quantity = (form.get("quantity") or "").strip()
        try:
            if not raw_quantity.isdecimal():
                raise ValueError
            quantity = int(raw_quantity)
            if not 1 <= quantity <= 2147483647:
                raise ValueError
            if quantity < job.quantity:
                errors["quantity"] = "Chỉ được tăng số lượng tuyển, không được giảm."
            data["quantity"] = quantity
        except ValueError:
            errors["quantity"] = "Số lượng tuyển phải là số nguyên dương hợp lệ."
    else:
        try:
            deadline = date.fromisoformat(form.get("application_deadline") or "")
            if deadline < date.today() or deadline < job.application_deadline:
                errors["application_deadline"] = "Chỉ được gia hạn, không được rút ngắn thời hạn."
            data["application_deadline"] = deadline
        except (TypeError, ValueError):
            errors["application_deadline"] = "Hạn nộp không hợp lệ."
    return data, errors


@recruiter_bp.route("/jobs/<int:job_id>/edit", methods=["POST"])
@role_required("RECRUITER")
def edit_job(job_id):
    """Lưu thay đổi ngay từ trang chi tiết tin tuyển dụng."""
    company = get_recruiter_company()
    if company is None:
        abort(404)
    detail_url = url_for("recruiter.job_detail", job_id=job_id)
    edit_url = url_for("recruiter.job_detail", job_id=job_id, edit=1)
    try:
        # Đọc lại dưới khóa, tránh dùng bộ đếm cũ khi hai request cùng lưu.
        job = (
            Job.query.filter_by(job_id=job_id, company_id=company.company_id)
            .populate_existing().with_for_update().first_or_404()
        )
        if get_job_display_status(job) != "OPEN":
            db.session.rollback()
            flash("Chỉ sửa được tin đang tuyển, còn hạn và không bị Admin ẩn.", "warning")
            return redirect(detail_url)

        # Locking read lấy dữ liệu mới nhất, kể cả hồ sơ đã rút.
        has_applications = False
        if request.form.get("action") == "edit_content":
            has_applications = db.session.query(Application.application_id).filter(
                Application.job_id == job_id
            ).with_for_update().first() is not None
        data, errors = validate_job_edit(request.form, job, has_applications)
        if errors:
            db.session.rollback()
            for message in errors.values():
                flash(message, "warning")
            return redirect(edit_url)

        # So sánh dữ liệu chuẩn hóa; không mất lượt vì định dạng hoặc xuống dòng.
        changes = {}
        for field, value in data.items():
            previous = getattr(job, field)
            if field in {"location", "working_time", "benefit"}:
                previous = normalize_job_edit_text(previous) or None
                value = normalize_job_edit_text(value) or None
            if previous != value:
                changes[field] = value
        if not changes:
            db.session.rollback()
            flash("Không có thay đổi nào cần lưu. Bạn không mất lượt chỉnh sửa.", "info")
            return redirect(detail_url)

        for field, value in changes.items():
            setattr(job, field, value)
        if request.form["action"] == "edit_content":
            job.content_edit_count += 1
        db.session.commit()
        messages = {
            "edit_content": "Cập nhật nội dung thành công. Bạn đã sử dụng lượt chỉnh sửa duy nhất.",
            "increase_quantity": "Tăng số lượng tuyển thành công. Không mất lượt chỉnh sửa nội dung.",
            "extend_deadline": "Gia hạn ứng tuyển thành công. Không mất lượt chỉnh sửa nội dung."
        }
        flash(messages[request.form["action"]], "success")
        return redirect(detail_url)
    except HTTPException:
        db.session.rollback()
        raise
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Không thể chỉnh sửa tin %s", job_id)
        flash("Không thể lưu thay đổi. Vui lòng thử lại.", "danger")
        return redirect(detail_url)
# ================= THÔNG TIN CÁ NHÂN RECRUITER =================

@recruiter_bp.route("/account", methods=["GET", "POST"])
@role_required("RECRUITER")
def account():
    """Xem và cập nhật thông tin cá nhân của Recruiter."""
    user = db.session.get(User, session["user_id"])
    if user is None or user.user_status != "ACTIVE":
        abort(403)

    if request.method == "POST":
        user_name = (request.form.get("user_name") or "").strip()
        phone = (request.form.get("phone") or "").strip()
        avatar_file = request.files.get("avatar")

        if not 2 <= len(user_name) <= 100:
            flash("Họ tên phải có từ 2 đến 100 ký tự.", "warning")
            return redirect(url_for("recruiter.account"))

        if phone and (not phone.isdigit() or not 9 <= len(phone) <= 15):
            flash("Số điện thoại phải gồm 9 đến 15 chữ số.", "warning")
            return redirect(url_for("recruiter.account"))

        avatar_path = None

        if avatar_file and avatar_file.filename:
            # Giới hạn dung lượng ảnh tải lên.
            image_bytes = avatar_file.read(3 * 1024 * 1024 + 1)
            if len(image_bytes) > 3 * 1024 * 1024:
                flash("Ảnh đại diện không được vượt quá 3 MB.", "warning")
                return redirect(url_for("recruiter.account"))

            try:
                # Kiểm tra nội dung ảnh thật, không tin phần mở rộng tệp.
                with Image.open(BytesIO(image_bytes)) as image:
                    image.verify()

                with Image.open(BytesIO(image_bytes)) as image:
                    if image.format not in ("JPEG", "PNG", "WEBP"):
                        raise ValueError("Định dạng không hỗ trợ.")

                    if image.width * image.height > 20_000_000:
                        raise ValueError("Kích thước ảnh quá lớn.")

                    # Chuẩn hóa ảnh để tránh lưu metadata không cần thiết.
                    image = image.convert("RGB")
                    image.thumbnail((512, 512))

                    folder = Path(current_app.static_folder) / "uploads" / "avatars"
                    folder.mkdir(parents=True, exist_ok=True)

                    filename = f"avatar_{secrets.token_hex(16)}.jpg"
                    destination = folder / filename
                    image.save(destination, format="JPEG", quality=85)

                    avatar_path = f"uploads/avatars/{filename}"

            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                flash("Ảnh không hợp lệ. Vui lòng chọn JPG, PNG hoặc WebP.", "warning")
                return redirect(url_for("recruiter.account"))

        try:
            user.user_name = user_name
            user.phone = phone or None

            if avatar_path:
                user.avatar = avatar_path

            db.session.commit()
            flash("Cập nhật thông tin cá nhân thành công.", "success")

        except Exception:
            db.session.rollback()

            # Nếu lưu CSDL thất bại thì xóa ảnh vừa tải lên.
            if avatar_path:
                (Path(current_app.static_folder) / avatar_path).unlink(missing_ok=True)

            current_app.logger.exception("Không thể cập nhật tài khoản Recruiter")
            flash("Không thể lưu thông tin. Vui lòng thử lại.", "danger")

        return redirect(url_for("recruiter.account"))

    return render_template("recruiter/account.html", user=user)


@recruiter_bp.route("/account/password", methods=["POST"])
@role_required("RECRUITER")
def change_password():
    """Đổi mật khẩu và trả lỗi về đúng trường nhập liệu."""

    user = db.session.get(User, session["user_id"])
    if user is None or user.user_status != "ACTIVE":
        abort(403)

    current_password = request.form.get("current_password") or ""
    new_password = request.form.get("new_password") or ""
    confirm_password = request.form.get("confirm_password") or ""

    errors = {}

    # Kiểm tra mật khẩu hiện tại
    if not current_password:
        errors["current_password"] = "Vui lòng nhập mật khẩu hiện tại."
    elif not user.check_password(current_password):
        errors["current_password"] = "Mật khẩu hiện tại không chính xác."

    # Kiểm tra mật khẩu mới theo quy tắc chung của JobFit
    if not new_password:
        errors["new_password"] = "Vui lòng nhập mật khẩu mới."
    else:
        password_error = validate_password(new_password)

        if password_error:
            errors["new_password"] = password_error
        elif len(new_password) > 128:
            errors["new_password"] = "Mật khẩu không được vượt quá 128 ký tự."
        elif user.check_password(new_password):
            errors["new_password"] = "Mật khẩu mới phải khác mật khẩu hiện tại."

    # Kiểm tra xác nhận mật khẩu
    if not confirm_password:
        errors["confirm_password"] = "Vui lòng xác nhận mật khẩu mới."
    elif new_password != confirm_password:
        errors["confirm_password"] = "Mật khẩu xác nhận không khớp."

    # Có lỗi: hiển thị trực tiếp trong form, không dùng Toast
    if errors:
        return render_template(
            "recruiter/account.html",
            user=user,
            password_errors=errors,
            show_password_form=True
        ), 400

    try:
        user.set_password(new_password)
        db.session.commit()

        # Chỉ hiện Toast khi cập nhật thành công
        flash("Đổi mật khẩu thành công.", "success")
        return redirect(url_for("recruiter.account"))

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Không thể đổi mật khẩu Recruiter")

        return render_template(
            "recruiter/account.html",
            user=user,
            password_errors={
                "general": "Không thể đổi mật khẩu. Vui lòng thử lại."
            },
            show_password_form=True
        ), 500

# ================= THÔNG TIN CÔNG TY RECRUITER =================

@recruiter_bp.route("/company", methods=["GET", "POST"])
@role_required("RECRUITER")
def company_profile():
    """Xem và chỉnh sửa công ty thuộc Recruiter đang đăng nhập."""

    user = db.session.get(User, session["user_id"])
    if user is None or user.user_status != "ACTIVE":
        abort(403)

    company = get_recruiter_company()
    if company is None:
        abort(404)

    errors = {}
    form_data = {}

    if request.method == "POST":
        form_data = {
            "company_name": (request.form.get("company_name") or "").strip(),
            "address": (request.form.get("address") or "").strip(),
            "website": (request.form.get("website") or "").strip(),
            "company_description": (request.form.get("company_description") or "").strip()
        }
        logo_file = request.files.get("logo")

        # Kiểm tra tên công ty
        if not 1 <= len(form_data["company_name"]) <= 150:
            errors["company_name"] = "Tên công ty phải có từ 1 đến 150 ký tự."

        # Kiểm tra địa chỉ
        if not 1 <= len(form_data["address"]) <= 255:
            errors["address"] = "Địa chỉ phải có từ 1 đến 255 ký tự."

        # Kiểm tra website
        website = form_data["website"]
        if website:
            try:
                parsed = urlsplit(website)
                if (
                    len(website) > 255
                    or parsed.scheme not in ("http", "https")
                    or not parsed.hostname
                    or parsed.username is not None
                    or parsed.password is not None
                    or any(char.isspace() for char in website)
                ):
                    raise ValueError
            except ValueError:
                errors["website"] = "Website phải là URL HTTP/HTTPS hợp lệ, tối đa 255 ký tự."

        # Giới hạn mô tả doanh nghiệp
        if len(form_data["company_description"]) > 5000:
            errors["company_description"] = "Mô tả không được vượt quá 5000 ký tự."

        logo_path = None

        if logo_file and logo_file.filename:
            image_bytes = logo_file.read(3 * 1024 * 1024 + 1)

            if len(image_bytes) > 3 * 1024 * 1024:
                errors["logo"] = "Logo không được vượt quá 3 MB."
            else:
                try:
                    # Xác thực nội dung ảnh thực tế
                    with Image.open(BytesIO(image_bytes)) as image:
                        image.verify()

                    with Image.open(BytesIO(image_bytes)) as image:
                        if image.format not in ("JPEG", "PNG", "WEBP"):
                            raise ValueError

                        if image.width * image.height > 20_000_000:
                            raise ValueError

                        # Chỉ lưu ảnh sau khi toàn bộ dữ liệu hợp lệ
                        if not errors:
                            image = image.convert("RGBA")
                            image.thumbnail((512, 512))

                            folder = Path(current_app.static_folder) / "uploads" / "companies"
                            folder.mkdir(parents=True, exist_ok=True)

                            filename = f"company_{secrets.token_hex(16)}.png"
                            destination = folder / filename
                            image.save(destination, format="PNG", optimize=True)

                            logo_path = f"uploads/companies/{filename}"

                except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                    errors["logo"] = "Logo không hợp lệ. Vui lòng chọn JPG, PNG hoặc WebP."

        if errors:
            return render_template(
                "recruiter/company.html",
                company=company,
                errors=errors,
                form_data=form_data,
                show_edit_form=True
            ), 400

        try:
            # Chỉ cập nhật công ty thuộc tài khoản hiện tại
            company.company_name = form_data["company_name"]
            company.address = form_data["address"]
            company.website = website or None
            company.company_description = form_data["company_description"] or None

            if logo_path:
                company.logo = logo_path

            db.session.commit()
            flash("Cập nhật thông tin công ty thành công.", "success")
            return redirect(url_for("recruiter.company_profile"))

        except Exception:
            db.session.rollback()

            # Dọn ảnh mới nếu lưu CSDL thất bại
            if logo_path:
                (Path(current_app.static_folder) / logo_path).unlink(missing_ok=True)

            current_app.logger.exception("Không thể cập nhật công ty Recruiter")
            errors["general"] = "Không thể lưu thông tin công ty. Vui lòng thử lại."

            return render_template(
                "recruiter/company.html",
                company=company,
                errors=errors,
                form_data=form_data,
                show_edit_form=True
            ), 500

    return render_template(
        "recruiter/company.html",
        company=company,
        errors={},
        form_data={},
        show_edit_form=False
    )

