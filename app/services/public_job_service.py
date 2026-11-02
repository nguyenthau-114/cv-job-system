#Chuẩn bị dữ liệu cho các trang Job/Company công khai.
"""Chuẩn bị dữ liệu đọc cho các trang việc làm và công ty công khai."""
from app.extensions import db
from app.models.company import Company
from app.models.job import Job
from app.models.user import User
from app.services.application_service import get_application_statuses
from app.services.job_service import company_website_url, job_card_data, load_job_data, visible_jobs
from app.services.saved_job_service import get_saved_job_ids


def cards_for_viewer(jobs, companies, skills, user_id=None):
    user = db.session.get(User, user_id) if user_id else None
    candidate = user if user and user.role == "CANDIDATE" and user.user_status == "ACTIVE" else None
    ids = [job.job_id for job in jobs]
    applied = get_application_statuses(candidate.user_id, ids) if candidate else {}
    saved = get_saved_job_ids(candidate.user_id, ids) if candidate else set()
    return [job_card_data(job, companies.get(job.company_id), skills.get(job.job_id, []),
                          saved=job.job_id in saved, application_status=applied.get(job.job_id)) for job in jobs]


def get_public_company_page(company_id, user_id=None, page=1):
    company = db.session.get(Company, company_id)
    if company is None:
        return None
    # Chỉ lọc và đếm trên nguồn tin công khai, không đưa tin ẩn vào View.
    query = visible_jobs().filter(Job.company_id == company.company_id).order_by(
        Job.job_created_at.desc(), Job.job_id.desc()
    )
    page = max(1, min(page, 2147483647))
    pagination = query.paginate(page=page, per_page=10, error_out=False)
    if pagination.total and not pagination.items and pagination.page > pagination.pages:
        pagination = query.paginate(page=pagination.pages, per_page=10, error_out=False)
    companies, skills = load_job_data(pagination.items)
    # Danh sách trường công khai tường minh, không truyền thông tin User của Recruiter.
    profile = {
        "id": company.company_id, "name": company.company_name,
        "logo": (company.logo or "").strip(),
        "description": (company.company_description or "").strip(),
        "address": (company.address or "").strip(),
        "website": company_website_url(company),
    }
    return {"company": profile, "pagination": pagination,
            "job_cards": cards_for_viewer(pagination.items, companies, skills, user_id)}
