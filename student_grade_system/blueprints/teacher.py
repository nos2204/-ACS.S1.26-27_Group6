# student_grade_system/blueprints/teacher.py
from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from persistence.models import (db, CourseSectionModel, EnrollmentModel, GradeModel, 
                                 GradeAppealModel, AttendanceModel, SemesterModel)
from gateway import token_required

teacher_bp = Blueprint('teacher', __name__)


@teacher_bp.route('/teacher/dashboard', endpoint='teacher_dashboard')
@token_required
def teacher_dashboard():
    """Dashboard riêng cho giảng viên - xem danh sách lớp học phần được phân công"""
    if session.get('role') != 'teacher':
        flash('Bạn không có quyền truy cập trang này!', 'danger')
        return redirect(url_for('dashboard'))
    
    from persistence.models import UserModel, TeacherModel
    user = UserModel.query.filter_by(username=session.get('username')).first()
    
    if not user or not user.teacher_id:
        flash('Tài khoản giảng viên chưa được liên kết!', 'warning')
        sections = []
    else:
        # Lấy các lớp học phần của giảng viên trong học kỳ hiện tại
        current_semester = SemesterModel.query.filter_by(is_current=True).first()
        query = CourseSectionModel.query.filter_by(teacher_id=user.teacher_id)
        if current_semester:
            query = query.filter_by(semester_id=current_semester.id)
        sections = query.order_by(CourseSectionModel.section_code).all()
    
    return render_template('teacher_dashboard.html', sections=sections)


@teacher_bp.route('/teacher/section/<int:section_id>/grades', endpoint='teacher_section_grades')
@token_required
def teacher_section_grades(section_id):
    """Bảng nhập điểm học phần theo danh sách sinh viên đăng ký"""
    if session.get('role') != 'teacher':
        flash('Bạn không có quyền truy cập trang này!', 'danger')
        return redirect(url_for('dashboard'))
    
    from persistence.models import UserModel, TeacherModel
    user = UserModel.query.filter_by(username=session.get('username')).first()
    
    section = CourseSectionModel.query.get_or_404(section_id)
    
    # Kiểm tra quyền: chỉ giảng viên của lớp hoặc admin mới được xem
    if session.get('role') != 'admin' and (not user or not user.teacher_id or section.teacher_id != user.teacher_id):
        flash('Bạn không có quyền xem điểm lớp học phần này!', 'danger')
        return redirect(url_for('teacher_dashboard'))
    
    # Lấy danh sách sinh viên đã đăng ký
    enrollments = EnrollmentModel.query.filter_by(
        section_id=section_id, 
        status='registered'
    ).all()
    
    # Lấy điểm của từng sinh viên
    grades_data = []
    for enrollment in enrollments:
        grade = GradeModel.query.filter_by(
            student_id=enrollment.student_id,
            subject_id=section.subject_id,
            semester_id=section.semester_id
        ).first()
        
        grades_data.append({
            'student': enrollment.student,
            'grade': grade
        })
    
    return render_template('teacher_grades.html', 
                         section=section, 
                         grades_data=grades_data)


@teacher_bp.route('/teacher/section/<int:section_id>/save_grades', methods=['POST'], endpoint='teacher_save_grades')
@token_required
def teacher_save_grades(section_id):
    """Lưu điểm học phần"""
    if session.get('role') != 'teacher':
        flash('Bạn không có quyền thực hiện thao tác này!', 'danger')
        return redirect(url_for('dashboard'))
    
    from persistence.models import UserModel, TeacherModel
    user = UserModel.query.filter_by(username=session.get('username')).first()
    
    section = CourseSectionModel.query.get_or_404(section_id)
    
    # Kiểm tra quyền
    if session.get('role') != 'admin' and (not user or not user.teacher_id or section.teacher_id != user.teacher_id):
        flash('Bạn không có quyền sửa điểm lớp học phần này!', 'danger')
        return redirect(url_for('teacher_dashboard'))
    
    # Kiểm tra xem điểm đã bị khóa chưa
    if section.grades_locked:
        flash('Điểm của lớp học phần này đã bị khóa, không thể sửa!', 'danger')
        return redirect(url_for('teacher_section_grades', section_id=section_id))
    
    # Lấy dữ liệu điểm từ form
    for key, value in request.form.items():
        if key.startswith('progress_'):
            student_id = int(key.split('_')[1])
            progress_grade = float(value) if value else 0.0
            
            # Tìm hoặc tạo grade record
            grade = GradeModel.query.filter_by(
                student_id=student_id,
                subject_id=section.subject_id,
                semester_id=section.semester_id
            ).first()
            
            if not grade:
                grade = GradeModel(
                    student_id=student_id,
                    subject_id=section.subject_id,
                    semester_id=section.semester_id
                )
                db.session.add(grade)
            
            grade.progress_grade = progress_grade
        
        elif key.startswith('exam_'):
            student_id = int(key.split('_')[1])
            exam_grade = float(value) if value else 0.0
            
            grade = GradeModel.query.filter_by(
                student_id=student_id,
                subject_id=section.subject_id,
                semester_id=section.semester_id
            ).first()
            
            if not grade:
                grade = GradeModel(
                    student_id=student_id,
                    subject_id=section.subject_id,
                    semester_id=section.semester_id
                )
                db.session.add(grade)
            
            grade.exam_grade = exam_grade
    
    db.session.commit()
    flash('Đã lưu điểm thành công!', 'success')
    return redirect(url_for('teacher_section_grades', section_id=section_id))


@teacher_bp.route('/teacher/section/<int:section_id>/lock', methods=['POST'], endpoint='teacher_lock_grades')
@token_required
def teacher_lock_grades(section_id):
    """Chốt/Khóa bảng điểm học phần"""
    if session.get('role') != 'teacher':
        flash('Bạn không có quyền thực hiện thao tác này!', 'danger')
        return redirect(url_for('dashboard'))
    
    from persistence.models import UserModel, TeacherModel
    user = UserModel.query.filter_by(username=session.get('username')).first()
    
    section = CourseSectionModel.query.get_or_404(section_id)
    
    # Kiểm tra quyền
    if session.get('role') != 'admin' and (not user or not user.teacher_id or section.teacher_id != user.teacher_id):
        flash('Bạn không có quyền khóa điểm lớp học phần này!', 'danger')
        return redirect(url_for('teacher_dashboard'))
    
    section.grades_locked = not section.grades_locked
    db.session.commit()
    
    status = 'đã khóa' if section.grades_locked else 'đã mở khóa'
    flash(f'Điểm của lớp {section.section_code} đã {status}!', 'success')
    return redirect(url_for('teacher_section_grades', section_id=section_id))


@teacher_bp.route('/teacher/appeals', endpoint='teacher_appeals')
@token_required
def teacher_appeals():
    """Xem và xử lý đơn phúc khảo cho các môn mình giảng dạy"""
    if session.get('role') != 'teacher':
        flash('Bạn không có quyền truy cập trang này!', 'danger')
        return redirect(url_for('dashboard'))
    
    from persistence.models import UserModel, TeacherModel
    user = UserModel.query.filter_by(username=session.get('username')).first()
    
    if not user or not user.teacher_id:
        flash('Tài khoản giảng viên chưa được liên kết!', 'warning')
        appeals = []
    else:
        # Lấy các lớp học phần của giảng viên
        section_ids = [s.id for s in CourseSectionModel.query.filter_by(teacher_id=user.teacher_id).all()]
        
        # Lấy các subject_id từ các lớp đó
        subject_ids = [s.subject_id for s in CourseSectionModel.query.filter(CourseSectionModel.id.in_(section_ids)).all()]
        
        # Lấy đơn phúc khảo cho các môn này
        if subject_ids:
            appeals = GradeAppealModel.query.filter(
                GradeAppealModel.subject_id.in_(subject_ids)
            ).order_by(GradeAppealModel.created_at.desc()).all()
        else:
            appeals = []
    
    return render_template('teacher_appeals.html', appeals=appeals)


@teacher_bp.route('/teacher/appeals/<int:appeal_id>/respond', methods=['POST'], endpoint='teacher_respond_appeal')
@token_required
def teacher_respond_appeal(appeal_id):
    """Phê duyệt/từ chối đơn phúc khảo"""
    if session.get('role') != 'teacher':
        flash('Bạn không có quyền thực hiện thao tác này!', 'danger')
        return redirect(url_for('dashboard'))
    
    from persistence.models import UserModel, TeacherModel
    user = UserModel.query.filter_by(username=session.get('username')).first()
    
    appeal = GradeAppealModel.query.get_or_404(appeal_id)
    
    # Kiểm tra quyền: chỉ giảng viên dạy môn đó mới được xử lý
    section = CourseSectionModel.query.filter_by(
        subject_id=appeal.subject_id,
        semester_id=appeal.semester_id
    ).first()
    
    if session.get('role') != 'admin' and (not user or not user.teacher_id or section.teacher_id != user.teacher_id):
        flash('Bạn không có quyền xử lý đơn phúc khảo này!', 'danger')
        return redirect(url_for('teacher_appeals'))
    
    status = request.form.get('status')
    response = request.form.get('response', '').strip()
    
    appeal.status = status
    appeal.response = response
    db.session.commit()
    
    flash('Đã xử lý đơn phúc khảo!', 'success')
    return redirect(url_for('teacher_appeals'))


@teacher_bp.route('/teacher/section/<int:section_id>/attendance', endpoint='teacher_attendance')
@token_required
def teacher_attendance(section_id):
    """Quản lý điểm danh sinh viên trong lớp học phần"""
    if session.get('role') != 'teacher':
        flash('Bạn không có quyền truy cập trang này!', 'danger')
        return redirect(url_for('dashboard'))
    
    from persistence.models import UserModel, TeacherModel
    user = UserModel.query.filter_by(username=session.get('username')).first()
    
    section = CourseSectionModel.query.get_or_404(section_id)
    
    # Kiểm tra quyền
    if session.get('role') != 'admin' and (not user or not user.teacher_id or section.teacher_id != user.teacher_id):
        flash('Bạn không có quyền xem điểm danh lớp học phần này!', 'danger')
        return redirect(url_for('teacher_dashboard'))
    
    # Lấy ngày được chọn (mặc định là hôm nay)
    selected_date_str = request.args.get('date')
    selected_date = None
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = date.today()
    else:
        selected_date = date.today()
    
    # Lấy danh sách sinh viên đã đăng ký
    enrollments = EnrollmentModel.query.filter_by(
        section_id=section_id, 
        status='registered'
    ).all()
    
    # Lấy điểm danh của từng sinh viên cho ngày được chọn
    attendance_data = []
    for enrollment in enrollments:
        attendance = AttendanceModel.query.filter_by(
            student_id=enrollment.student_id,
            section_id=section_id,
            date=selected_date
        ).first()
        
        attendance_data.append({
            'student': enrollment.student,
            'attendance': attendance
        })
    
    return render_template('teacher_attendance.html',
                         section=section,
                         attendance_data=attendance_data,
                         selected_date=selected_date)


@teacher_bp.route('/teacher/section/<int:section_id>/save_attendance', methods=['POST'], endpoint='teacher_save_attendance')
@token_required
def teacher_save_attendance(section_id):
    """Lưu điểm danh"""
    if session.get('role') != 'teacher':
        flash('Bạn không có quyền thực hiện thao tác này!', 'danger')
        return redirect(url_for('dashboard'))
    
    from persistence.models import UserModel, TeacherModel
    user = UserModel.query.filter_by(username=session.get('username')).first()
    
    section = CourseSectionModel.query.get_or_404(section_id)
    
    # Kiểm tra quyền
    if session.get('role') != 'admin' and (not user or not user.teacher_id or section.teacher_id != user.teacher_id):
        flash('Bạn không có quyền sửa điểm danh lớp học phần này!', 'danger')
        return redirect(url_for('teacher_dashboard'))
    
    selected_date_str = request.form.get('date')
    selected_date = None
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = date.today()
    else:
        selected_date = date.today()
    
    # Lấy dữ liệu điểm danh từ form
    for key, value in request.form.items():
        if key.startswith('attendance_'):
            student_id = int(key.split('_')[1])
            status = value
            
            # Tìm hoặc tạo attendance record
            attendance = AttendanceModel.query.filter_by(
                student_id=student_id,
                section_id=section_id,
                date=selected_date
            ).first()
            
            if not attendance:
                attendance = AttendanceModel(
                    student_id=student_id,
                    section_id=section_id,
                    date=selected_date
                )
                db.session.add(attendance)
            
            attendance.status = status
            attendance.notes = request.form.get(f'notes_{student_id}', '').strip()
    
    db.session.commit()
    flash('Đã lưu điểm danh thành công!', 'success')
    return redirect(url_for('teacher_attendance', section_id=section_id, date=selected_date_str))
