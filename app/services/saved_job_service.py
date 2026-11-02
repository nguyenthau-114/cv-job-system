#Candidate lưu và bỏ lưu việc làm.
"""Lưu tin độc lập với Application và vòng đời CV."""
from flask import current_app
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.job import Job
from app.models.saved_job import SavedJob
from app.models.user import User
from app.services.application_service import get_application_statuses
from app.services.job_service import job_availability, job_card_data, load_job_data


def get_saved_job_ids(user_id, job_ids):
    if not job_ids:
        return set()
    return {row.job_id for row in db.session.query(SavedJob.job_id).filter(
        SavedJob.user_id == user_id, SavedJob.job_id.in_(job_ids)
    ).all()}


def set_saved_job(user_id, job_id, is_saved):
    """Đặt trạng thái đích để request gửi lại không đảo lưu thành bỏ lưu."""
    if type(is_saved) is not bool or type(job_id) is not int or not 1 <= job_id <= 2147483647:
        return None, {"saved_job": "Yêu cầu lưu tin không hợp lệ."}
    try:
        # Cùng khóa User đầu tiên với luồng ứng tuyển, sau đó Job → SavedJob.
        user = User.query.filter_by(user_id=user_id).populate_existing().with_for_update().first()
        if user is None or user.role != "CANDIDATE" or user.user_status != "ACTIVE":
            db.session.rollback()
            return None, {"account": "Chỉ Candidate đang hoạt động được lưu hoặc bỏ lưu tin."}
        job = Job.query.filter_by(job_id=job_id).populate_existing().with_for_update().first()
        existing = SavedJob.query.filter_by(user_id=user_id, job_id=job_id).with_for_update().first()
        if is_saved:
            if existing is not None:
                db.session.rollback()
                return True, {}
            if job_availability(job) != "OPEN":
                db.session.rollback()
                return None, {"job": "Tin tuyển dụng hiện không còn khả dụng."}
            db.session.add(SavedJob(user_id=user_id, job_id=job_id))
            db.session.commit()
        elif existing is not None:
            db.session.delete(existing)
            db.session.commit()
        else:
            db.session.rollback()
        return is_saved, {}
    except IntegrityError:
        db.session.rollback()
        # UNIQUE bảo vệ cả nguồn ghi không dùng khóa User của Service.
        try:
            exists = SavedJob.query.filter_by(user_id=user_id, job_id=job_id).first() is not None
        except SQLAlchemyError:
            exists = False
        finally:
            db.session.rollback()
        if is_saved and exists:
            return True, {}
        return None, {"database": "Không thể thay đổi trạng thái lưu tin. Vui lòng thử lại."}
    except SQLAlchemyError as error:
        db.session.rollback()
        current_app.logger.error("Không thể lưu hoặc bỏ lưu tin (%s).", type(error).__name__)
        return None, {"database": "Không thể thay đổi trạng thái lưu tin. Vui lòng thử lại."}


def get_saved_jobs(user_id, page=1):
    query = SavedJob.query.filter_by(user_id=user_id).order_by(
        SavedJob.saved_at.desc(), SavedJob.saved_job_id.desc()
    )
    pagination = query.paginate(page=max(1, page), per_page=10, error_out=False)
    if pagination.total and not pagination.items and pagination.page > pagination.pages:
        pagination = query.paginate(page=pagination.pages, per_page=10, error_out=False)
    saved = pagination.items
    job_ids = [item.job_id for item in saved]
    jobs = {job.job_id: job for job in Job.query.filter(Job.job_id.in_(job_ids)).all()} if job_ids else {}
    safe_jobs = [job for job in jobs.values() if job_availability(job) != "UNAVAILABLE"]
    companies, skills = load_job_data(safe_jobs)
    applications = get_application_statuses(user_id, job_ids)
    cards = [job_card_data(
        jobs.get(item.job_id), companies.get(jobs[item.job_id].company_id) if item.job_id in jobs else None,
        skills.get(item.job_id, []), job_id=item.job_id, saved=True, saved_at=item.saved_at,
        application_status=applications.get(item.job_id),
    ) for item in saved]
    return cards, pagination
