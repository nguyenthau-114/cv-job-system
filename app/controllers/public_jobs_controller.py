
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, render_template, request
from sqlalchemy import and_, or_
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.company import Company
from app.models.job import Job
from app.models.job_category import JobCategory
from app.models.job_skill import JobSkill
from app.models.skill import Skill

public_jobs_bp = Blueprint("public_jobs", __name__)

WORK_MODES = {
    "ONSITE": "Tại văn phòng",
    "REMOTE": "Làm việc từ xa",
    "HYBRID": "Kết hợp"
}
JOB_TYPES = {
    "FULL_TIME": "Toàn thời gian",
    "PART_TIME": "Bán thời gian",
    "INTERNSHIP": "Thực tập"
}
LEVELS = {
    "INTERN": "Intern",
    "FRESHER": "Fresher",
    "JUNIOR": "Junior",
    "MIDDLE": "Middle",
    "SENIOR": "Senior",
    "LEAD": "Lead"
}
SORT_OPTIONS = {
    "newest": "Mới nhất",
    "oldest": "Cũ nhất",
    "deadline": "Sắp hết hạn"
}


def visible_jobs():
    # Chỉ công khai tin đang tuyển, chưa bị ẩn và còn hạn.
    return Job.query.filter(
        Job.job_status == "OPEN",
        Job.is_hidden.is_(False),
        Job.application_deadline >= date.today()
    )


def salary_value(name):
    """Đọc mức lương triệu VND và đổi sang VND."""
    raw = request.args.get(name, "").strip()
    if not raw:
        return None
    try:
        value = Decimal(raw)
        if not value.is_finite() or value < 0 or value > 1000000:
            return None
        return value * 1000000
    except (InvalidOperation, ValueError):
        return None


def load_job_data(jobs):
    """Lấy thông tin công ty và kỹ năng cho cả trang."""
    job_ids = [job.job_id for job in jobs]
    company_ids = {job.company_id for job in jobs}
    companies = {}
    skills_by_job = {job_id: [] for job_id in job_ids}

    if company_ids:
        companies = {
            company.company_id: company
            for company in Company.query.filter(
                Company.company_id.in_(company_ids)
            ).all()
        }

    if job_ids:
        rows = (
            db.session.query(
                JobSkill.job_id,
                JobSkill.requirement_type,
                Skill.skill_name
            )
            .join(Skill, Skill.skill_id == JobSkill.skill_id)
            .filter(JobSkill.job_id.in_(job_ids))
            .order_by(Skill.skill_name.asc())
            .all()
        )
        for job_id, requirement_type, skill_name in rows:
            skills_by_job[job_id].append({
                "name": skill_name,
                "type": requirement_type
            })

    return companies, skills_by_job


def salary_text(job):
    """Hiển thị lương theo triệu VND."""
    minimum = job.min_salary
    maximum = job.max_salary

    def fmt(value):
        return f"{value / Decimal('1000000'):g}"

    if minimum is not None and maximum is not None:
        return f"{fmt(minimum)} - {fmt(maximum)} triệu"
    if minimum is not None:
        return f"Từ {fmt(minimum)} triệu"
    if maximum is not None:
        return f"Đến {fmt(maximum)} triệu"
    return "Thỏa thuận"


@public_jobs_bp.route("/jobs")
def index():
    # Đọc tham số GET, không tin tưởng giá trị từ URL.
    keyword = request.args.get("keyword", "").strip()[:150]
    location = request.args.get("location", "").strip()[:150]
    category_id = request.args.get("category", type=int)
    skill_id = request.args.get("skill", type=int)
    work_mode = request.args.get("work_mode", "").strip()
    job_type = request.args.get("job_type", "").strip()
    level = request.args.get("level", "").strip()
    sort = request.args.get("sort", "newest")
    page = max(1, request.args.get("page", 1, type=int))
    min_salary = salary_value("min_salary")
    max_salary = salary_value("max_salary")

    if work_mode not in WORK_MODES:
        work_mode = ""
    if job_type not in JOB_TYPES:
        job_type = ""
    if level not in LEVELS:
        level = ""
    if sort not in SORT_OPTIONS:
        sort = "newest"

    query = visible_jobs()

    if keyword:
        pattern = f"%{keyword}%"
        matching_skill_jobs = (
            db.session.query(JobSkill.job_id)
            .join(Skill, Skill.skill_id == JobSkill.skill_id)
            .filter(Skill.skill_name.ilike(pattern))
        )
        query = query.filter(
            or_(
                Job.job_title.ilike(pattern),
                Job.job_description.ilike(pattern),
                Job.job_requirement.ilike(pattern),
                Job.company_id.in_(
                    db.session.query(Company.company_id).filter(
                        Company.company_name.ilike(pattern)
                    )
                ),
                Job.job_id.in_(matching_skill_jobs)
            )
        )

    if location:
        query = query.filter(Job.location.ilike(f"%{location}%"))

    if category_id is not None:
        query = query.filter(Job.job_category_id == category_id)

    if skill_id is not None:
        query = query.filter(
            Job.job_id.in_(
                db.session.query(JobSkill.job_id).filter(
                    JobSkill.skill_id == skill_id
                )
            )
        )

    if work_mode:
        query = query.filter(Job.work_mode == work_mode)
    if job_type:
        query = query.filter(Job.job_type == job_type)
    if level:
        query = query.filter(Job.level == level)

    # Lọc theo khoảng lương có giao nhau với mức người dùng chọn.
    # Tin lương thỏa thuận không tham gia lọc theo mức lương.
    if min_salary is not None:
        query = query.filter(
            or_(
                Job.max_salary >= min_salary,
                and_(Job.max_salary.is_(None), Job.min_salary >= min_salary)
            )
        )
    if max_salary is not None:
        query = query.filter(
            or_(
                Job.min_salary <= max_salary,
                and_(Job.min_salary.is_(None), Job.max_salary <= max_salary)
            )
        )
    if min_salary is not None and max_salary is not None:
        query = query.filter(
            or_(Job.min_salary.isnot(None), Job.max_salary.isnot(None))
        )

    if sort == "oldest":
        query = query.order_by(Job.job_created_at.asc(), Job.job_id.asc())
    elif sort == "deadline":
        query = query.order_by(
            Job.application_deadline.asc(), Job.job_id.desc()
        )
    else:
        query = query.order_by(
            Job.job_created_at.desc(), Job.job_id.desc()
        )

    pagination = query.paginate(
        page=page, per_page=10, error_out=False
    )
    jobs = pagination.items
    companies, skills_by_job = load_job_data(jobs)

    categories = JobCategory.query.order_by(
        JobCategory.category_name.asc()
    ).all()
    skills = Skill.query.filter(
        Skill.skill_status == "ACTIVE"
    ).order_by(Skill.skill_name.asc()).all()

    filters = {
        "keyword": keyword,
        "location": location,
        "category": category_id,
        "skill": skill_id,
        "work_mode": work_mode,
        "job_type": job_type,
        "level": level,
        "min_salary": request.args.get("min_salary", ""),
        "max_salary": request.args.get("max_salary", ""),
        "sort": sort
    }

    # Giữ các bộ lọc hiện tại khi chuyển trang.
    page_params = {
        key: value for key, value in filters.items()
        if value is not None and value != ""
    }

    return render_template(
        "jobs/index.html",
        jobs=jobs,
        pagination=pagination,
        categories=categories,
        skills=skills,
        companies=companies,
        skills_by_job=skills_by_job,
        filters=filters,
        page_params=page_params,
        work_modes=WORK_MODES,
        job_types=JOB_TYPES,
        levels=LEVELS,
        sort_options=SORT_OPTIONS,
        salary_text=salary_text
    )


@public_jobs_bp.route("/jobs/<int:job_id>")
def show(job_id):
    # Không để lộ thông tin tin đã đóng hoặc bị ẩn qua URL.
    job = visible_jobs().filter(Job.job_id == job_id).first()
    if job is None:
        abort(404)

    companies, skills_by_job = load_job_data([job])
    category = db.session.get(JobCategory, job.job_category_id)

    return render_template(
        "jobs/show.html",
        job=job,
        company=companies.get(job.company_id),
        category=category,
        job_skills=skills_by_job.get(job.job_id, []),
        work_modes=WORK_MODES,
        job_types=JOB_TYPES,
        salary_text=salary_text
    )
