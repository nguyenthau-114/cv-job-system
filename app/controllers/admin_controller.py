#Dashboard Admin, quản lý tài khoản và tin tuyển dụng. Gọi Model/Service liên quan.
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from sqlalchemy import or_, and_, func
from app.middleware.auth_middleware import role_required
from app.models.user import User
from app.models.company import Company
from app.models.job import Job
from app.extensions import db


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

@admin_bp.route("/")
@role_required("ADMIN")
def dashboard():
    today = date.today()

    # Thống kê tổng quan hệ thống
    statistics = {
        "candidates": User.query.filter_by(role="CANDIDATE").count(),
        "recruiters": User.query.filter_by(role="RECRUITER").count(),
        "companies": Company.query.count(),
        "locked_users": User.query.filter_by(user_status="LOCKED").count(),
        "total_jobs": Job.query.count(),
        "open_jobs": Job.query.filter(
            Job.job_status == "OPEN",
            Job.application_deadline >= today,
            Job.is_hidden.is_(False)
        ).count(),
        "hidden_jobs": Job.query.filter_by(is_hidden=True).count(),
        "expired_jobs": Job.query.filter(
            (Job.job_status == "EXPIRED") |
            ((Job.job_status == "OPEN") & (Job.application_deadline < today))
        ).count()
    }

    # Xác định tháng đầu tiên trong 6 tháng gần nhất
    first_month = today.replace(day=1) - relativedelta(months=5)

    # Đếm số tin được tạo theo từng tháng từ MySQL
    rows = db.session.query(
        func.year(Job.job_created_at).label("year"),
        func.month(Job.job_created_at).label("month"),
        func.count(Job.job_id).label("total")
    ).filter(
        Job.job_created_at >= datetime.combine(first_month, datetime.min.time())
    ).group_by(
        func.year(Job.job_created_at),
        func.month(Job.job_created_at)
    ).all()

    # Chuyển kết quả truy vấn thành dữ liệu biểu đồ
    monthly_counts = {
        (row.year, row.month): row.total for row in rows
    }

    monthly_labels = []
    monthly_values = []

    for offset in range(6):
        month_date = first_month + relativedelta(months=offset)
        monthly_labels.append(f"T{month_date.month}/{month_date.year}")
        monthly_values.append(
            monthly_counts.get((month_date.year, month_date.month), 0)
        )

    return render_template(
        "admin/dashboard.html",
        statistics=statistics,
        monthly_labels=monthly_labels,
        monthly_values=monthly_values,
        now=today
    )


@admin_bp.route("/users", methods=["GET"])
@role_required("ADMIN")
def users():
    # Lấy các điều kiện tìm kiếm từ URL
    keyword = request.args.get("q", "").strip()
    role = request.args.get("role", "").strip().upper()
    status = request.args.get("status", "").strip().upper()

    # Chỉ quản lý ứng viên và nhà tuyển dụng
    query = User.query.filter(User.role.in_(["CANDIDATE", "RECRUITER"]))

    if keyword:
        search = f"%{keyword}%"
        query = query.filter(or_(
            User.user_name.ilike(search),
            User.email.ilike(search)
        ))

    if role in ["CANDIDATE", "RECRUITER"]:
        query = query.filter(User.role == role)

    if status in ["ACTIVE", "LOCKED"]:
        query = query.filter(User.user_status == status)

    # Sắp xếp tài khoản mới nhất lên trước
    accounts = query.order_by(
        User.user_created_at.desc(),
        User.user_id.desc()
    ).all()

    statistics = {
        "total": User.query.filter(User.role.in_(["CANDIDATE", "RECRUITER"])).count(),
        "candidates": User.query.filter_by(role="CANDIDATE").count(),
        "recruiters": User.query.filter_by(role="RECRUITER").count(),
        "locked": User.query.filter(
            User.role.in_(["CANDIDATE", "RECRUITER"]),
            User.user_status == "LOCKED"
        ).count()
    }

    return render_template(
         "admin/users.html",
        accounts=accounts,
        statistics=statistics,
        keyword=keyword,
        selected_role=role,
        selected_status=status
    )

@admin_bp.route("/users/<int:user_id>/toggle-status", methods=["POST"])
@role_required("ADMIN")
def toggle_user_status(user_id):
    account = db.session.get(User, user_id)

    if account is None:
        flash("Không tìm thấy tài khoản.", "danger")
        return redirect(url_for("admin.users"))

    # Chỉ cho phép khóa/mở khóa Candidate và Recruiter
    if account.role not in ["CANDIDATE", "RECRUITER"]:
        flash("Không được thay đổi trạng thái tài khoản Admin.", "danger")
        return redirect(url_for("admin.users"))

    if account.user_id == session.get("user_id"):
        flash("Bạn không thể tự khóa tài khoản của mình.", "danger")
        return redirect(url_for("admin.users"))

    if account.user_status not in ["ACTIVE", "LOCKED"]:
        flash("Trạng thái tài khoản không hợp lệ.", "danger")
        return redirect(url_for("admin.users"))

    if account.user_status == "ACTIVE":
        account.user_status = "LOCKED"
        message = "Khóa tài khoản thành công."
    else:
        account.user_status = "ACTIVE"
        message = "Mở khóa tài khoản thành công."

    try:
        db.session.commit()
        flash(message, "success")
    except Exception:
        db.session.rollback()
        flash("Không thể cập nhật trạng thái tài khoản.", "danger")

    return redirect(url_for("admin.users"))


# ================= QUẢN LÝ TIN TUYỂN DỤNG =================

@admin_bp.route("/jobs", methods=["GET"])
@role_required("ADMIN")
def jobs():
    keyword = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip().upper()
    visibility = request.args.get("visibility", "").strip().upper()
    today = date.today()

    # Kết hợp Job và Company để lấy tên công ty
    query = db.session.query(Job, Company).join(
        Company, Job.company_id == Company.company_id
    )

    # Tìm theo tên công việc hoặc tên công ty
    if keyword:
        search = f"%{keyword}%"
        query = query.filter(or_(
            Job.job_title.ilike(search),
            Company.company_name.ilike(search)
        ))

    # Trạng thái tuyển dụng: ưu tiên CLOSED trước EXPIRED
    if status == "OPEN":
        query = query.filter(
            Job.job_status == "OPEN",
            Job.application_deadline >= today
        )
    elif status == "CLOSED":
        query = query.filter(Job.job_status == "CLOSED")

    elif status == "EXPIRED":
        query = query.filter(or_(
            Job.job_status == "EXPIRED",
            and_(
                Job.job_status == "OPEN",
                Job.application_deadline < today
            )
        ))
    # Trạng thái hiển thị do Admin quản lý
    if visibility == "HIDDEN":
        query = query.filter(Job.is_hidden.is_(True))
    elif visibility == "VISIBLE":
        query = query.filter(Job.is_hidden.is_(False))

    records = query.order_by(
        Job.job_created_at.desc(),
        Job.job_id.desc()
    ).all()

    # Tổng quan toàn hệ thống, không phụ thuộc bộ lọc
    statistics = {
        "total": Job.query.count(),
        "open": Job.query.filter(
            Job.job_status == "OPEN",
            Job.application_deadline >= today,
            Job.is_hidden.is_(False)
        ).count(),
        "hidden": Job.query.filter(Job.is_hidden.is_(True)).count(),
        "closed": Job.query.filter(Job.job_status == "CLOSED").count()
    }

    # Chuẩn hóa dữ liệu để template không cần truy vấn thêm
    job_items = []
    for job, company in records:
        if job.job_status == "CLOSED":
            display_status = "CLOSED"
        elif job.job_status == "EXPIRED" or (
            job.job_status == "OPEN" and job.application_deadline < today
        ):
            display_status = "EXPIRED"
        else:
            display_status = job.job_status

        job_items.append({
            "job": job,
            "company": company,
            "display_status": display_status
        })

    return render_template(
        "admin/jobs.html",
        job_items=job_items,
        statistics=statistics,
        keyword=keyword,
        selected_status=status,
        selected_visibility=visibility
    )


@admin_bp.route("/jobs/<int:job_id>/toggle-visibility", methods=["POST"])
@role_required("ADMIN")
def toggle_job_visibility(job_id):
    from app.services.job_moderation_service import set_job_visibility
    if request.files or set(request.form) - {"is_hidden", "csrf_token"} or any(
        len(request.form.getlist(key)) != 1 for key in request.form
    ) or request.form.get("is_hidden") not in {"0", "1"}:
        flash("Yêu cầu không hợp lệ. Vui lòng tải lại trang.", "danger")
        return redirect(url_for("admin.jobs"))
    success, message = set_job_visibility(session["user_id"], job_id, request.form["is_hidden"] == "1")
    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.jobs"))
