#Admin ẩn/hiện Job và phát sinh thông báo tương ứng.
"""Admin đặt trạng thái hiển thị tường minh và thông báo trong cùng transaction."""
from uuid import uuid4
from sqlalchemy.exc import SQLAlchemyError
from flask import current_app
from app.extensions import db
from app.models.job import Job
from app.models.company import Company
from app.services.notification_service import lock_event_users, add_notification


def set_job_visibility(actor_id, job_id, is_hidden):
    if type(is_hidden) is not bool:
        return False, 'Trạng thái hiển thị không hợp lệ.'
    try:
        recipient = db.session.query(Company.user_id).join(Job).filter(Job.job_id == job_id).scalar()
        users = lock_event_users(actor_id, recipient)
        actor = users.get(actor_id)
        if actor is None or actor.role != 'ADMIN' or actor.user_status != 'ACTIVE':
            db.session.rollback()
            return False, 'Bạn không có quyền quản lý tin.'
        row = db.session.query(Job, Company.user_id).join(Company).filter(Job.job_id == job_id).populate_existing().with_for_update().first()
        if row is None or row[1] != recipient:
            db.session.rollback()
            return False, 'Không tìm thấy tin hoặc quyền sở hữu vừa thay đổi.'
        job = row[0]
        if bool(job.is_hidden) == is_hidden:
            db.session.rollback()
            return True, 'Trạng thái hiển thị không thay đổi.'
        job.is_hidden = is_hidden
        event_type = 'JOB_HIDDEN' if is_hidden else 'JOB_SHOWN'
        add_notification(recipient, event_type, f'job:{job_id}:visibility:{uuid4().hex}', job_id=job_id)
        db.session.commit()
        return True, 'Đã ẩn tin tuyển dụng.' if is_hidden else 'Đã bỏ ẩn tin tuyển dụng.'
    except SQLAlchemyError as error:
        db.session.rollback()
        current_app.logger.error('Không thể cập nhật hiển thị Job (%s).', type(error).__name__)
        return False, 'Không thể cập nhật trạng thái hiển thị.'
