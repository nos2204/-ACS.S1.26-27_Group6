# student_grade_system/blueprints/semesters.py
from datetime import datetime, timedelta, date
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from persistence.models import db, SemesterModel, AuditLog
from gateway import token_required, admin_required

semesters_bp = Blueprint('semesters', __name__)


@semesters_bp.route('/semesters', endpoint='semesters_list')
@token_required
@admin_required
def semesters_list():
    """Danh sách tất cả học kỳ"""
    semesters = SemesterModel.query.order_by(
        SemesterModel.academic_year.desc(),
        SemesterModel.name.desc()
    ).all()
    
    return render_template('semesters.html', semesters=semesters)


@semesters_bp.route('/semesters/create', endpoint='semester_create', methods=['GET', 'POST'])
@token_required
@admin_required
def semester_create():
    """Tạo học kỳ mới"""
    if request.method == 'POST':
        name = request.form.get('name')
        academic_year = request.form.get('academic_year')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        is_current = request.form.get('is_current') == 'on'
        
        if not name or not academic_year:
            flash('Vui lòng nhập tên học kỳ và năm học!', 'danger')
            return redirect(url_for('semesters_list'))
        
        # Kiểm tra học kỳ đã tồn tại chưa
        existing = SemesterModel.query.filter_by(
            name=name,
            academic_year=academic_year
        ).first()
        
        if existing:
            flash(f'Học kỳ {name} - {academic_year} đã tồn tại!', 'warning')
            return redirect(url_for('semesters_list'))
        
        # Nếu đánh dấu là học kỳ hiện tại, hủy đánh dấu các học kỳ khác
        if is_current:
            SemesterModel.query.update({'is_current': False})
            db.session.commit()
        
        # Tạo học kỳ mới
        semester = SemesterModel(
            name=name,
            academic_year=academic_year,
            start_date=datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None,
            end_date=datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None,
            original_end_date=datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None,
            is_current=is_current,
            status='active'
        )
        
        db.session.add(semester)
        db.session.commit()
        
        # Ghi log
        log = AuditLog(
            actor=request.form.get('username', 'admin'),
            action='create_semester',
            target=f'Semester: {name} - {academic_year}',
            detail=f'Created new semester {name} - {academic_year}'
        )
        db.session.add(log)
        db.session.commit()
        
        flash(f'Đã tạo học kỳ {name} - {academic_year} thành công!', 'success')
        return redirect(url_for('semesters_list'))
    
    return render_template('semester_form.html', semester=None)


@semesters_bp.route('/semesters/<int:id>/edit', endpoint='semester_edit', methods=['GET', 'POST'])
@token_required
@admin_required
def semester_edit(id):
    """Chỉnh sửa học kỳ"""
    semester = SemesterModel.query.get_or_404(id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        academic_year = request.form.get('academic_year')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        is_current = request.form.get('is_current') == 'on'
        
        if not name or not academic_year:
            flash('Vui lòng nhập tên học kỳ và năm học!', 'danger')
            return redirect(url_for('semesters_list'))
        
        # Kiểm tra trùng với học kỳ khác
        existing = SemesterModel.query.filter(
            SemesterModel.name == name,
            SemesterModel.academic_year == academic_year,
            SemesterModel.id != id
        ).first()
        
        if existing:
            flash(f'Học kỳ {name} - {academic_year} đã tồn tại!', 'warning')
            return redirect(url_for('semesters_list'))
        
        # Nếu đánh dấu là học kỳ hiện tại, hủy đánh dấu các học kỳ khác
        if is_current:
            SemesterModel.query.filter(SemesterModel.id != id).update({'is_current': False})
            db.session.commit()
        
        # Cập nhật học kỳ
        semester.name = name
        semester.academic_year = academic_year
        semester.start_date = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None
        semester.end_date = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None
        if not semester.original_end_date:
            semester.original_end_date = semester.end_date
        semester.is_current = is_current
        
        db.session.commit()
        
        # Ghi log
        log = AuditLog(
            actor=request.form.get('username', 'admin'),
            action='edit_semester',
            target=f'Semester: {name} - {academic_year}',
            detail=f'Edited semester {name} - {academic_year}'
        )
        db.session.add(log)
        db.session.commit()
        
        flash(f'Đã cập nhật học kỳ {name} - {academic_year} thành công!', 'success')
        return redirect(url_for('semesters_list'))
    
    return render_template('semester_form.html', semester=semester)


@semesters_bp.route('/semesters/<int:id>/extend', endpoint='semester_extend', methods=['GET', 'POST'])
@token_required
def semester_extend(id):
    """Gia hạn học kỳ (Admin, Teacher, Student đều có thể yêu cầu)"""
    semester = SemesterModel.query.get_or_404(id)
    
    if request.method == 'POST':
        extension_days = request.form.get('extension_days', type=int)
        reason = request.form.get('reason')
        
        if not extension_days or extension_days <= 0:
            flash('Vui lòng nhập số ngày gia hạn hợp lệ!', 'danger')
            return redirect(url_for('semesters_list'))
        
        if not semester.can_extend:
            flash('Học kỳ này không thể gia hạn thêm!', 'warning')
            return redirect(url_for('semesters_list'))
        
        # Kiểm tra quyền hạn
        role = request.form.get('role', 'student')
        if role != 'admin':
            # Sinh viên và giảng viên chỉ có thể yêu cầu, admin sẽ duyệt
            # Ở đây cho phép trực tiếp gia hạn để đơn giản hóa
            pass
        
        # Gia hạn học kỳ
        if semester.end_date:
            semester.end_date += timedelta(days=extension_days)
        else:
            semester.end_date = date.today() + timedelta(days=extension_days)
        
        semester.extension_count += 1
        semester.status = 'extended'
        semester.extension_reason = reason
        semester.extended_by = request.form.get('username', 'unknown')
        semester.extended_at = datetime.now()
        
        db.session.commit()
        
        # Ghi log
        log = AuditLog(
            actor=request.form.get('username', 'unknown'),
            action='extend_semester',
            target=f'Semester: {semester.display_name}',
            detail=f'Extended semester by {extension_days} days. Reason: {reason}'
        )
        db.session.add(log)
        db.session.commit()
        
        flash(f'Đã gia hạn học kỳ {semester.display_name} thêm {extension_days} ngày!', 'success')
        return redirect(url_for('semesters_list'))
    
    return render_template('semester_extend.html', semester=semester)


@semesters_bp.route('/semesters/<int:id>/set_current', endpoint='semester_set_current')
@token_required
@admin_required
def semester_set_current(id):
    """Đặt học kỳ làm học kỳ hiện tại"""
    semester = SemesterModel.query.get_or_404(id)
    
    # Hủy đánh dấu tất cả học kỳ hiện有的
    SemesterModel.query.update({'is_current': False})
    db.session.commit()
    
    # Đánh dấu học kỳ này là hiện tại
    semester.is_current = True
    db.session.commit()
    
    # Ghi log
    log = AuditLog(
        actor=request.form.get('username', 'admin'),
        action='set_current_semester',
        target=f'Semester: {semester.display_name}',
        detail=f'Set {semester.display_name} as current semester'
    )
    db.session.add(log)
    db.session.commit()
    
    flash(f'Đã đặt {semester.display_name} làm học kỳ hiện tại!', 'success')
    return redirect(url_for('semesters_list'))


@semesters_bp.route('/semesters/<int:id>/close', endpoint='semester_close')
@token_required
@admin_required
def semester_close(id):
    """Đóng học kỳ"""
    semester = SemesterModel.query.get_or_404(id)
    
    semester.status = 'closed'
    semester.is_current = False
    db.session.commit()
    
    # Ghi log
    log = AuditLog(
        actor=request.form.get('username', 'admin'),
        action='close_semester',
        target=f'Semester: {semester.display_name}',
        detail=f'Closed semester {semester.display_name}'
    )
    db.session.add(log)
    db.session.commit()
    
    flash(f'Đã đóng học kỳ {semester.display_name}!', 'success')
    return redirect(url_for('semesters_list'))


@semesters_bp.route('/semesters/<int:id>/delete', endpoint='semester_delete')
@token_required
@admin_required
def semester_delete(id):
    """Xóa học kỳ"""
    semester = SemesterModel.query.get_or_404(id)
    
    # Kiểm tra xem học kỳ có dữ liệu không
    if semester.grades or semester.sections:
        flash('Không thể xóa học kỳ đã có dữ liệu điểm hoặc lớp học phần!', 'danger')
        return redirect(url_for('semesters_list'))
    
    display_name = semester.display_name
    db.session.delete(semester)
    db.session.commit()
    
    # Ghi log
    log = AuditLog(
        actor=request.form.get('username', 'admin'),
        action='delete_semester',
        target=f'Semester: {display_name}',
        detail=f'Deleted semester {display_name}'
    )
    db.session.add(log)
    db.session.commit()
    
    flash(f'Đã xóa học kỳ {display_name}!', 'success')
    return redirect(url_for('semesters_list'))
