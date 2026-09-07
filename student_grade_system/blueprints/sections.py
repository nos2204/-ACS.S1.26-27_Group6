# student_grade_system/blueprints/sections.py
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort
from persistence.models import (db, CourseSectionModel, SubjectModel, SemesterModel,
                                 TeacherModel, UserModel, EnrollmentModel, GradeModel)
from business.student_service import StudentService
from gateway import token_required, admin_required, admin_or_teacher_required

sections_bp = Blueprint('sections', __name__)


@sections_bp.route('/course-sections', endpoint='course_sections_manager')
@token_required
@admin_required
def course_sections_manager():
    sections = CourseSectionModel.query.order_by(CourseSectionModel.section_code).all()
    subjects = SubjectModel.query.order_by(SubjectModel.subject_name).all()
    semesters = SemesterModel.query.order_by(SemesterModel.academic_year.desc(), SemesterModel.name).all()
    teachers = TeacherModel.query.order_by(TeacherModel.full_name).all()
    return render_template('course_sections.html', sections=sections, subjects=subjects, semesters=semesters, teachers=teachers)


@sections_bp.route('/course-sections/add', methods=['POST'], endpoint='add_course_section')
@token_required
@admin_required
def add_course_section():
    code = request.form.get('section_code', '').strip()
    if not code:
        flash('Vui lòng nhập mã lớp học phần!', 'danger')
        return redirect(url_for('course_sections_manager'))
    if CourseSectionModel.query.filter_by(section_code=code).first():
        flash(f'Mã lớp học phần "{code}" đã tồn tại!', 'danger')
        return redirect(url_for('course_sections_manager'))

    day = request.form.get('schedule_day', '').strip()
    shift = request.form.get('schedule_shift', '').strip()
    custom = request.form.get('schedule_custom', '').strip()

    if custom:
        schedule_str = custom
    elif day and shift:
        schedule_str = f"{day} - {shift}"
    elif day:
        schedule_str = day
    else:
        schedule_str = request.form.get('schedule', '').strip() or None

    section = CourseSectionModel(section_code=code,
                                 subject_id=request.form.get('subject_id'),
                                 semester_id=request.form.get('semester_id'),
                                 teacher_id=request.form.get('teacher_id') or None,
                                 max_students=request.form.get('max_students', type=int) or 50,
                                 room=request.form.get('room', '').strip() or None,
                                 schedule=schedule_str,
                                 status=request.form.get('status', 'open'))
    db.session.add(section)
    db.session.commit()
    flash('Đã thêm lớp học phần!', 'success')
    return redirect(url_for('course_sections_manager'))


@sections_bp.route('/course-sections/<int:section_id>/delete', methods=['POST'], endpoint='delete_course_section')
@token_required
@admin_required
def delete_course_section(section_id):
    section = CourseSectionModel.query.get_or_404(section_id)
    if section.enrollments:
        flash('Không thể xóa lớp học phần đã có sinh viên đăng ký!', 'danger')
        return redirect(url_for('course_sections_manager'))
    db.session.delete(section)
    db.session.commit()
    flash('Đã xóa lớp học phần!', 'success')
    return redirect(url_for('course_sections_manager'))


@sections_bp.route('/course-sections/<int:section_id>/toggle_lock', methods=['POST'], endpoint='toggle_section_lock')
@token_required
@admin_required
def toggle_section_lock(section_id):
    section = CourseSectionModel.query.get_or_404(section_id)
    section.grades_locked = not section.grades_locked
    if section.grades_locked:
        section.status = 'locked'
    db.session.commit()
    flash('Đã cập nhật trạng thái khóa điểm!', 'success')
    return redirect(url_for('course_sections_manager'))


@sections_bp.route('/enrollments', endpoint='enrollments_page')
@token_required
def enrollments_page():
    sections = CourseSectionModel.query.order_by(CourseSectionModel.section_code).all()
    user = UserModel.query.filter_by(username=session.get('username')).first()
    my_enrollments = []
    registered_section_ids = set()
    conflicting_section_ids = set()

    if user and user.student_id:
        my_enrollments = EnrollmentModel.query.filter_by(student_id=user.student_id).all()
        registered_section_ids = {e.section_id for e in my_enrollments if e.status == 'registered'}

        for s in sections:
            if s.id not in registered_section_ids:
                is_conflict, _ = StudentService.check_schedule_conflict(user.student_id, s)
                if is_conflict:
                    conflicting_section_ids.add(s.id)

    filter_day = request.args.get('day', '').strip()
    filter_shift = request.args.get('shift', '').strip()
    hide_conflict = request.args.get('hide_conflict') == '1'

    filtered_sections = []
    for s in sections:
        if hide_conflict and s.id in conflicting_section_ids:
            continue

        sched_text = (s.schedule or '').lower()
        if filter_day and filter_day.lower() not in sched_text:
            continue
        if filter_shift and filter_shift.lower() not in sched_text:
            continue

        filtered_sections.append(s)

    return render_template('enrollments.html',
                           sections=filtered_sections,
                           my_enrollments=my_enrollments,
                           registered_section_ids=registered_section_ids,
                           conflicting_section_ids=conflicting_section_ids,
                           filter_day=filter_day,
                           filter_shift=filter_shift,
                           hide_conflict=hide_conflict)


@sections_bp.route('/enrollments/register/<int:section_id>', methods=['POST'], endpoint='register_section')
@token_required
def register_section(section_id):
    if session.get('role') != 'student':
        abort(403)
    user = UserModel.query.filter_by(username=session.get('username')).first()
    if not user or not user.student_id:
        flash('Tài khoản chưa liên kết sinh viên!', 'danger')
        return redirect(url_for('enrollments_page'))
    section = CourseSectionModel.query.get_or_404(section_id)
    if section.status != 'open':
        flash('Lớp học phần này chưa mở đăng ký hoặc đã đóng!', 'danger')
        return redirect(url_for('enrollments_page'))
    if section.is_full:
        flash('Lớp học phần đã đủ sĩ số!', 'danger')
        return redirect(url_for('enrollments_page'))

    # 1. Kiểm tra môn học tiên quyết
    if section.subject:
        prereqs_met, missing_prereqs = StudentService.check_prerequisites_met(user.student_id, section.subject)
        if not prereqs_met:
            missing_str = ', '.join(missing_prereqs)
            flash(f'Không thể đăng ký: Chưa hoàn thành môn tiên quyết ({missing_str})!', 'danger')
            return redirect(url_for('enrollments_page'))

    # 2. Kiểm tra trùng lịch học
    is_conflict, conflict_msg = StudentService.check_schedule_conflict(user.student_id, section)
    if is_conflict:
        flash(f'Không thể đăng ký: {conflict_msg}!', 'danger')
        return redirect(url_for('enrollments_page'))

    existed = EnrollmentModel.query.filter_by(student_id=user.student_id, section_id=section_id).first()
    if existed:
        if existed.status != 'registered':
            existed.status = 'registered'
            db.session.commit()
            flash('Đã đăng ký lại học phần!', 'success')
        else:
            flash('Bạn đã đăng ký lớp học phần này rồi!', 'warning')
        return redirect(url_for('enrollments_page'))
    enrollment = EnrollmentModel(student_id=user.student_id, section_id=section_id)
    db.session.add(enrollment)
    db.session.commit()
    flash('Đăng ký học phần thành công!', 'success')
    return redirect(url_for('enrollments_page'))


@sections_bp.route('/enrollments/cancel/<int:enrollment_id>', methods=['POST'], endpoint='cancel_enrollment')
@token_required
def cancel_enrollment(enrollment_id):
    if session.get('role') != 'student':
        abort(403)
    user = UserModel.query.filter_by(username=session.get('username')).first()
    enrollment = EnrollmentModel.query.get_or_404(enrollment_id)
    if not user or enrollment.student_id != user.student_id:
        abort(403)
    if enrollment.section.status != 'open':
        flash('Không thể hủy vì lớp học phần đã đóng đăng ký!', 'danger')
        return redirect(url_for('enrollments_page'))
    db.session.delete(enrollment)
    db.session.commit()
    flash('Đã hủy đăng ký học phần!', 'success')
    return redirect(url_for('enrollments_page'))


@sections_bp.route('/teacher/sections', endpoint='teacher_sections')
@token_required
@admin_or_teacher_required
def teacher_sections():
    user = UserModel.query.filter_by(username=session.get('username')).first()
    if session.get('role') == 'admin':
        sections = CourseSectionModel.query.order_by(CourseSectionModel.section_code).all()
    else:
        sections = CourseSectionModel.query.filter_by(teacher_id=user.teacher_id).order_by(CourseSectionModel.section_code).all()
    return render_template('teacher_sections.html', sections=sections)


@sections_bp.route('/teacher/sections/<int:section_id>/grades', methods=['GET', 'POST'], endpoint='section_grades')
@token_required
@admin_or_teacher_required
def section_grades(section_id):
    section = CourseSectionModel.query.get_or_404(section_id)
    user = UserModel.query.filter_by(username=session.get('username')).first()
    if session.get('role') == 'teacher' and section.teacher_id != user.teacher_id:
        abort(403)
    enrollments = EnrollmentModel.query.filter_by(section_id=section_id, status='registered').all()
    if request.method == 'POST':
        if section.grades_locked and session.get('role') != 'admin':
            flash('Điểm lớp này đã bị khóa. Vui lòng liên hệ admin.', 'danger')
            return redirect(url_for('section_grades', section_id=section_id))
        for e in enrollments:
            pg = request.form.get(f'progress_{e.student_id}', type=float)
            eg = request.form.get(f'exam_{e.student_id}', type=float)
            if pg is None or eg is None:
                continue
            if not (0 <= pg <= 10 and 0 <= eg <= 10):
                flash('Điểm phải nằm trong khoảng 0 đến 10!', 'danger')
                return redirect(url_for('section_grades', section_id=section_id))
            StudentService.upsert_grade(e.student_id, section.subject_id, section.semester_id, pg, eg, actor=session.get('username', 'teacher'))
        flash('Đã lưu điểm lớp học phần!', 'success')
        return redirect(url_for('section_grades', section_id=section_id))
    grade_map = {}
    for e in enrollments:
        grade_map[e.student_id] = GradeModel.query.filter_by(student_id=e.student_id, subject_id=section.subject_id, semester_id=section.semester_id).first()
    return render_template('section_grades.html', section=section, enrollments=enrollments, grade_map=grade_map)
