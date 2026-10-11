# gateway.py  —  API Gateway: xác thực, phân quyền, CSRF, brute-force guard
import os
import sys
import secrets
import hashlib

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import jwt
from functools import wraps
from datetime import datetime, timedelta
from flask import session, flash, redirect, url_for, request, abort


def generate_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']


def validate_csrf():
    if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
        token       = session.get('csrf_token')
        form_token  = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
        if not token or not form_token:
            abort(403, description='CSRF token thiếu.')
        if not secrets.compare_digest(
            hashlib.sha256(token.encode()).hexdigest(),
            hashlib.sha256(form_token.encode()).hexdigest()
        ):
            abort(403, description='CSRF token không hợp lệ.')


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = session.get('token')
        if not token:
            flash('Chưa đăng nhập hoặc phiên làm việc đã hết hạn!', 'danger')
            return redirect(url_for('login'))
        try:
            from flask import current_app
            secret    = current_app.secret_key or os.getenv('FLASK_SECRET_KEY', 'quanlidiemsinhvien_secret_key_2026')
            data      = jwt.decode(token, secret, algorithms=['HS256'])
            request.user_data = data
        except jwt.ExpiredSignatureError:
            session.clear()
            flash('Phiên làm việc đã hết hạn, vui lòng đăng nhập lại!', 'danger')
            return redirect(url_for('login'))
        except jwt.InvalidTokenError:
            session.clear()
            flash('Token không hợp lệ!', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('Chỉ tài khoản Admin mới được thực hiện chức năng này!', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


def admin_or_self_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') == 'admin':
            return f(*args, **kwargs)
        target_id = kwargs.get('student_id')
        if target_id and str(session.get('linked_student_id')) == str(target_id):
            return f(*args, **kwargs)
        flash('Bạn không có quyền truy cập tài nguyên này!', 'danger')
        return redirect(url_for('dashboard'))
    return decorated


def admin_or_self_or_teacher_required(f):
    """Cho phép admin, sinh viên xem điểm của mình, hoặc giáo viên xem điểm sinh viên"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') == 'admin':
            return f(*args, **kwargs)
        target_id = kwargs.get('student_id')
        if target_id and str(session.get('linked_student_id')) == str(target_id):
            return f(*args, **kwargs)
        if session.get('role') == 'teacher':
            return f(*args, **kwargs)
        flash('Bạn không có quyền truy cập tài nguyên này!', 'danger')
        return redirect(url_for('dashboard'))
    return decorated


def teacher_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'teacher':
            flash('Chỉ tài khoản Giảng viên mới được thực hiện chức năng này!', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


def admin_or_teacher_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') not in ['admin', 'teacher']:
            flash('Bạn không có quyền thực hiện chức năng này!', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


MAX_FAILED   = 5
LOCKOUT_MINS = 15


def check_brute_force(user):
    if not user:
        return False, None
    if user.is_locked():
        remaining = user.locked_until - datetime.utcnow()
        mins = max(1, int(remaining.total_seconds() // 60))
        return True, f"{mins} phút"
    return False, None


def record_failed_login(user):
    if not user:
        return
    from persistence.models import db
    user.failed_login_count = (user.failed_login_count or 0) + 1
    if user.failed_login_count >= MAX_FAILED:
        user.locked_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_MINS)
    db.session.commit()


def record_success_login(user):
    from persistence.models import db
    user.reset_lock()
    db.session.commit()