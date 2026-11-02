#API và trang thông báo, đánh dấu đã đọc, đồng bộ chuông.
from flask import Blueprint, request, session, g, jsonify, render_template, redirect, url_for, abort
from sqlalchemy.exc import SQLAlchemyError
from app.extensions import db
from app.models.notification import Notification
from app.services.notification_service import get_sync_data, get_notifications, mark_read, notification_target, get_notification_viewer

notifications_bp = Blueprint('notifications', __name__, url_prefix='/notifications')


@notifications_bp.before_request
def require_notification_user():
    user, inbox = get_notification_viewer(session.get('user_id'), load_inbox=request.endpoint == 'notifications.sync')
    if user is None or user.user_status != 'ACTIVE' or user.role not in {'CANDIDATE', 'RECRUITER'}:
        if request.endpoint == 'notifications.index' and user is None:
            return redirect(url_for('auth.login'))
        return jsonify(success=False, errors={'account': 'Phiên đăng nhập không hợp lệ hoặc tài khoản không được phép truy cập.'}), 401 if user is None else 403
    g.notification_user = user
    g.notification_inbox = inbox


@notifications_bp.after_request
def no_notification_cache(response):
    response.headers['Cache-Control'] = 'private, no-store'
    return response


@notifications_bp.errorhandler(SQLAlchemyError)
def unavailable(error):
    db.session.rollback()
    return jsonify(success=False, errors={'database': 'Chưa thể tải thông báo. Vui lòng thử lại sau.'}), 503


@notifications_bp.route('')
def index():
    items, pagination, state = get_notifications(g.notification_user.user_id, request.args.get('page', 1, type=int), request.args.get('state', 'all'))
    template = 'notifications/candidate.html' if g.notification_user.role == 'CANDIDATE' else 'notifications/recruiter.html'
    return render_template(template, notifications=items, pagination=pagination, state=state)


@notifications_bp.route('/sync')
def sync():
    values = request.args.get('applications', '')
    if len(values) > 600:
        abort(400)
    parts = values.split(',') if values else []
    if len(parts) > 50 or any(not p.isascii() or not p.isdecimal() or not 1 <= int(p) <= 2147483647 for p in parts):
        abort(400)
    return jsonify(success=True, **get_sync_data(g.notification_user, sorted({int(p) for p in parts}),
        request.args.get('summary') == '1', inbox=g.notification_inbox))


def valid_read_form():
    return not request.files and not set(request.form) - {'csrf_token'} and all(len(request.form.getlist(k)) == 1 for k in request.form)


@notifications_bp.route('/<int:notification_id>/read', methods=['POST'])
def read_notification(notification_id):
    if not valid_read_form():
        abort(400)
    if not mark_read(g.notification_user.user_id, notification_id):
        db.session.rollback()
        abort(404)
    db.session.commit()
    return jsonify(success=True)


@notifications_bp.route('/read-all', methods=['POST'])
def read_all():
    if not valid_read_form():
        abort(400)
    if not mark_read(g.notification_user.user_id):
        db.session.rollback()
        abort(403)
    db.session.commit()
    return jsonify(success=True)


@notifications_bp.route('/<int:notification_id>/open', methods=['POST'])
def open_notification(notification_id):
    if not valid_read_form():
        abort(400)
    notification = Notification.query.filter_by(notification_id=notification_id, user_id=g.notification_user.user_id).first()
    if notification is None:
        abort(404)
    target = notification_target(g.notification_user, notification)
    if not mark_read(g.notification_user.user_id, notification_id):
        db.session.rollback()
        abort(404)
    db.session.commit()
    # Mở thông báo không gọi luồng mở Application và không đánh dấu VIEWED.
    return redirect(target or url_for('notifications.index'), code=303)
