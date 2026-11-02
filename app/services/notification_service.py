#Tạo, lưu, chống trùng, truy vấn và đánh dấu thông báo.
"""Thông báo bền vững: dùng transaction của nghiệp vụ, không commit riêng."""
from flask import url_for
from sqlalchemy import and_, case, false, func, true
from sqlalchemy.orm import aliased

from app.extensions import db
from app.models.notification import Notification
from app.models.user import User
from app.models.application import Application
from app.models.company import Company
from app.models.job import Job
from app.services.job_service import job_availability

MESSAGES = {
    'APP_SUBMITTED': 'Bạn có hồ sơ ứng tuyển mới.',
    'APP_VIEWED': 'Hồ sơ ứng tuyển của bạn đã được nhà tuyển dụng xem.',
    'APP_CONSIDERING': 'Hồ sơ ứng tuyển của bạn đang được xem xét.',
    'APP_REJECTED': 'Nhà tuyển dụng đã từ chối hồ sơ ứng tuyển của bạn.',
    'APP_WITHDRAWN': 'Ứng viên đã rút một hồ sơ ứng tuyển.',
    'JOB_HIDDEN': 'Admin đã ẩn một tin tuyển dụng của bạn.',
    'JOB_SHOWN': 'Admin đã hiện lại một tin tuyển dụng của bạn.',
}


def lock_event_users(actor_id, recipient_id=None):
    """Khóa tất cả User theo ID trước CV/Job, tránh đảo khóa FK người nhận."""
    users = {}
    for identifier in sorted({i for i in (actor_id, recipient_id) if i is not None}):
        user = User.query.filter_by(user_id=identifier).populate_existing().with_for_update(
            read=identifier != actor_id
        ).first()
        if user is not None:
            users[identifier] = user
    return users


def add_notification(user_id, event_type, event_key, application_id=None, job_id=None):
    if event_type not in MESSAGES:
        raise ValueError('Unknown notification event')
    exists = db.session.query(Notification.notification_id).filter_by(user_id=user_id, event_key=event_key).first()
    if exists is not None:
        return False
    db.session.add(Notification(user_id=user_id, application_id=application_id, job_id=job_id,
        event_type=event_type, event_key=event_key, notification_message=MESSAGES[event_type], is_read=False))
    return True


def notification_target(user, notification):
    if notification.application_id:
        query = db.session.query(Application.application_id).filter(Application.application_id == notification.application_id)
        if user.role == 'CANDIDATE':
            query = query.filter(Application.user_id == user.user_id)
            endpoint = 'candidate.application_detail'
        else:
            query = query.join(Job).join(Company).filter(Company.user_id == user.user_id)
            endpoint = 'recruiter.application_detail'
        if query.first():
            return url_for(endpoint, application_id=notification.application_id)
    elif notification.job_id and user.role == 'RECRUITER':
        if db.session.query(Job.job_id).join(Company).filter(
            Job.job_id == notification.job_id, Company.user_id == user.user_id
        ).first():
            return url_for('recruiter.job_detail', job_id=notification.job_id)
    return None


def notification_data(notification):
    # Không truyền message tự do hoặc tên Job cũ; dữ liệu LEGACY dùng lời nhắc an toàn.
    return {'id': notification.notification_id, 'message': MESSAGES.get(notification.event_type, 'Bạn có một thông báo từ JobFit.'),
            'is_read': notification.is_read, 'created_at': notification.notification_created_at.isoformat(),
            'open_url': url_for('notifications.open_notification', notification_id=notification.notification_id),
            'read_url': url_for('notifications.read_notification', notification_id=notification.notification_id)}


def get_notifications(user_id, page=1, state='all'):
    state = state if state in {'all', 'read', 'unread'} else 'all'
    query = Notification.query.filter_by(user_id=user_id)
    if state != 'all':
        query = query.filter(Notification.is_read == (true() if state == 'read' else false()))
    index = 'ix_notification_user_latest' if state == 'all' else 'ix_notification_user_unread'
    query = query.with_hint(Notification, f'USE INDEX ({index})', dialect_name='mysql').order_by(Notification.notification_id.desc())
    pagination = query.paginate(page=max(1, min(page, 2147483647)), per_page=10, error_out=False)
    if pagination.total and not pagination.items:
        pagination = query.paginate(page=pagination.pages, per_page=10, error_out=False)
    return [notification_data(item) for item in pagination.items], pagination, state


def get_notification_viewer(user_id, load_inbox=False):
    """Kiểm tra tài khoản mới nhất, ghép hộp thư vào cùng query của polling."""
    if not load_inbox:
        return db.session.query(User.user_id, User.role, User.user_status).filter_by(user_id=user_id).first(), None
    latest_query = Notification.query.filter_by(user_id=user_id).with_hint(
        Notification, 'USE INDEX (ix_notification_user_latest)', dialect_name='mysql'
    ).order_by(Notification.notification_id.desc()).limit(8).subquery()
    latest = aliased(Notification, latest_query)
    unread_query = db.session.query(func.count(Notification.notification_id)).filter(
        Notification.user_id == user_id, Notification.is_read == false()
    ).correlate(None).scalar_subquery()
    rows = db.session.query(User.user_id, User.role, User.user_status, latest, unread_query).select_from(User).outerjoin(
        latest, latest.user_id == User.user_id).filter(User.user_id == user_id).order_by(latest.notification_id.desc()).all()
    if not rows:
        return None, None
    return rows[0], (rows[0][4], [row[3] for row in rows if row[3] is not None])


def get_sync_data(user, application_ids, include_summary=False, inbox=None):
    # Số query cố định, không tải toàn bộ hộp thư hoặc gọi N query theo từng thông báo.
    if inbox is None:
        _, inbox = get_notification_viewer(user.user_id, load_inbox=True)
    unread, latest = inbox
    states, summary = [], None
    include_summary = include_summary and user.role == 'CANDIDATE'
    if application_ids or include_summary:
        fields = [Application.application_id, Application.application_status,
            Job.job_id, Job.job_title, Job.is_hidden, Job.job_status, Job.application_deadline,
            Company.company_name]
        if include_summary:
            counts = db.session.query(func.count(Application.application_id).label('applications'),
                func.coalesce(func.sum(case((Application.application_status.in_(
                    ('SUBMITTED', 'VIEWED', 'CONSIDERING', 'INTERVIEW')), 1), else_=0)), 0).label('reviewing'),
                func.coalesce(func.sum(case((Application.application_status == 'VIEWED', 1), else_=0)), 0).label('viewed')
            ).filter(Application.user_id == user.user_id).subquery()
            # Một aggregate và LEFT JOIN giữ cả thống kê khi danh sách rỗng.
            query = db.session.query(*fields, counts.c.applications, counts.c.reviewing, counts.c.viewed).select_from(
                counts).outerjoin(Application, and_(Application.user_id == user.user_id,
                    Application.application_id.in_(application_ids))).outerjoin(
                        Job, Job.job_id == Application.job_id).outerjoin(Company, Company.company_id == Job.company_id)
        else:
            query = db.session.query(*fields).select_from(Application).join(Job, Job.job_id == Application.job_id).join(
                Company, Company.company_id == Job.company_id).filter(Application.application_id.in_(application_ids))
            query = query.filter(Application.user_id == user.user_id) if user.role == 'CANDIDATE' else query.filter(Company.user_id == user.user_id)
        for row in query.all():
            if include_summary:
                summary = {'applications': int(row.applications), 'reviewing': int(row.reviewing), 'viewed': int(row.viewed)}
            if row.application_id is None:
                continue
            status = row.application_status
            can_process = user.role == 'RECRUITER' and not row.is_hidden and row.job_status in {'OPEN', 'CLOSED', 'EXPIRED'}
            states.append({'id': row.application_id, 'status': status if status in {
                'SUBMITTED', 'VIEWED', 'CONSIDERING', 'INTERVIEW', 'REJECTED', 'WITHDRAWN'} else 'UNKNOWN',
                'job_status': 'HIDDEN' if row.is_hidden else job_availability(row),
                'can_replace': user.role == 'CANDIDATE' and status == 'SUBMITTED',
                'can_withdraw': user.role == 'CANDIDATE' and status in {'SUBMITTED', 'VIEWED', 'CONSIDERING', 'INTERVIEW'},
                'can_consider': can_process and status == 'VIEWED',
                'can_reject': can_process and status in {'VIEWED', 'CONSIDERING'},
                'job_title': row.job_title if user.role == 'RECRUITER' or not row.is_hidden else 'Tin tuyển dụng hiện không còn khả dụng.',
                'company_name': row.company_name if user.role == 'RECRUITER' or not row.is_hidden else '',
                'public_job_url': url_for('public_jobs.show', job_id=row.job_id) if not row.is_hidden and job_availability(row) == 'OPEN' else None})
    return {'viewer': str(user.user_id), 'role': user.role, 'unread': unread,
            'latest': [notification_data(n) for n in latest], 'applications': states, 'summary': summary}


def mark_read(user_id, notification_id=None):
    # Cùng khóa User với bên tạo: thông báo đến sau điểm xử lý vẫn chưa đọc.
    user = lock_event_users(user_id).get(user_id)
    if user is None or user.user_status != 'ACTIVE' or user.role not in {'CANDIDATE', 'RECRUITER'}:
        return False
    query = Notification.query.filter_by(user_id=user_id)
    if notification_id is not None:
        query = query.filter_by(notification_id=notification_id)
        if query.first() is None:
            return False
    query.filter_by(is_read=False).update({'is_read': True}, synchronize_session=False)
    return True
