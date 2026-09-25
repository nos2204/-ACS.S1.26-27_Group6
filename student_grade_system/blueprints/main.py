# student_grade_system/blueprints/main.py
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from persistence.models import db, StudentModel, SemesterModel
from business.analytics_service import AnalyticsService
from business.grade_service import GradeService
from gateway import token_required

main_bp = Blueprint('main', __name__)


@main_bp.route('/', endpoint='dashboard')
@token_required
def dashboard():
    stats = AnalyticsService.get_dashboard_stats()
    return render_template('dashboard.html', **stats)


@main_bp.route('/profile', methods=['GET', 'POST'], endpoint='my_profile')
@token_required
def my_profile():
    if session.get('role') != 'student':
        flash('Chỉ tài khoản sinh viên mới có trang hồ sơ cá nhân.', 'warning')
        return redirect(url_for('dashboard'))

    linked_student_id = session.get('linked_student_id')

    if not linked_student_id:
        flash('Tài khoản này chưa được liên kết với sinh viên.', 'danger')
        return redirect(url_for('dashboard'))

    student = StudentModel.query.get(linked_student_id)

    if not student:
        flash('Không tìm thấy thông tin sinh viên được liên kết.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip() or None
        phone = request.form.get('phone', '').strip() or None
        addr  = request.form.get('address', '').strip() or None
        student.email   = email
        student.phone   = phone
        student.address = addr
        db.session.commit()
        flash('Đã cập nhật thông tin cá nhân!', 'success')
        return redirect(url_for('my_profile'))

    semesters = SemesterModel.query.order_by(SemesterModel.academic_year.desc()).all()
    warnings    = GradeService.get_student_warnings(student.id)
    total_avg10 = GradeService.calculate_student_avg10(student.id)
    return render_template('profile.html', student=student, semesters=semesters, warnings=warnings, total_avg10=total_avg10)
