# student_grade_system/blueprints/admin.py
import tempfile
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, send_file
from persistence.models import (db, SubjectModel, SemesterModel, DepartmentModel,
                                 ClassModel, TeacherModel, UserModel, GradeModel, AuditLog, StudentModel)
from business.report_service import ReportService
from gateway import token_required, admin_required

admin_bp = Blueprint('admin', __name__)


# ===================== MÔN HỌC =====================
@admin_bp.route('/subjects', endpoint='subjects_manager')
@token_required
@admin_required
def subjects_manager():
    subjects    = SubjectModel.query.order_by(SubjectModel.subject_code).all()
    departments = DepartmentModel.query.order_by(DepartmentModel.department_name).all()
    return render_template('subjects.html', subjects=subjects, departments=departments)


@admin_bp.route('/subjects/add', methods=['POST'], endpoint='add_subject')
@token_required
@admin_required
def add_subject():
    code = request.form.get('subject_code', '').strip()
    if SubjectModel.query.filter_by(subject_code=code).first():
        flash(f'Mã môn học "{code}" đã tồn tại!', 'danger')
        return redirect(url_for('subjects_manager'))

    pw = float(request.form.get('progress_weight', 0.4) or 0.4)
    ew = float(request.form.get('exam_weight', 0.6) or 0.6)

    subject = SubjectModel(
        subject_code    = code,
        subject_name    = request.form.get('subject_name', '').strip(),
        credits         = int(request.form.get('credits', 3)),
        department_id   = request.form.get('department_id') or None,
        progress_weight = pw,
        exam_weight     = ew,
    )
    prereq_ids = request.form.getlist('prerequisites', type=int)
    if prereq_ids:
        prereqs = SubjectModel.query.filter(SubjectModel.id.in_(prereq_ids)).all()
        subject.prerequisites = prereqs

    db.session.add(subject)
    db.session.commit()
    flash('Đã thêm môn học!', 'success')
    return redirect(url_for('subjects_manager'))


@admin_bp.route('/subjects/<int:subject_id>/edit', methods=['POST'], endpoint='edit_subject')
@token_required
@admin_required
def edit_subject(subject_id):
    subject = SubjectModel.query.get_or_404(subject_id)
    subject.subject_name  = request.form.get('subject_name', subject.subject_name).strip()
    subject.credits       = int(request.form.get('credits', subject.credits))
    subject.department_id = request.form.get('department_id') or None
    if 'progress_weight' in request.form:
        subject.progress_weight = float(request.form.get('progress_weight', 0.4) or 0.4)
    if 'exam_weight' in request.form:
        subject.exam_weight = float(request.form.get('exam_weight', 0.6) or 0.6)

    prereq_ids = request.form.getlist('prerequisites', type=int)
    if prereq_ids is not None:
        prereqs = SubjectModel.query.filter(SubjectModel.id.in_(prereq_ids)).all()
        subject.prerequisites = [p for p in prereqs if p.id != subject_id]

    db.session.commit()
    flash('Đã cập nhật môn học!', 'success')
    return redirect(url_for('subjects_manager'))


@admin_bp.route('/subjects/<int:subject_id>/delete', methods=['POST'], endpoint='delete_subject')
@token_required
@admin_required
def delete_subject(subject_id):
    subject = SubjectModel.query.get_or_404(subject_id)
    db.session.delete(subject)
    db.session.commit()
    flash('Đã xóa môn học.', 'success')
    return redirect(url_for('subjects_manager'))


# ===================== HỌC KỲ =====================
@admin_bp.route('/semesters', endpoint='semesters_manager')
@token_required
@admin_required
def semesters_manager():
    semesters = SemesterModel.query.order_by(
        SemesterModel.academic_year.desc(), SemesterModel.name
    ).all()
    return render_template('semesters.html', semesters=semesters)


@admin_bp.route('/semesters/add', methods=['POST'], endpoint='add_semester')
@token_required
@admin_required
def add_semester():
    name  = request.form.get('name', '').strip()
    year  = request.form.get('academic_year', '').strip()
    is_cur = bool(request.form.get('is_current'))

    if SemesterModel.query.filter_by(name=name, academic_year=year).first():
        flash('Học kỳ này đã tồn tại!', 'danger')
        return redirect(url_for('semesters_manager'))

    if is_cur:
        SemesterModel.query.update({'is_current': False})

    sem = SemesterModel(name=name, academic_year=year, is_current=is_cur)
    db.session.add(sem)
    db.session.commit()
    flash(f'Đã thêm {sem.display_name}.', 'success')
    return redirect(url_for('semesters_manager'))


@admin_bp.route('/semesters/<int:sem_id>/set_current', methods=['POST'], endpoint='set_current_semester')
@token_required
@admin_required
def set_current_semester(sem_id):
    SemesterModel.query.update({'is_current': False})
    sem = SemesterModel.query.get_or_404(sem_id)
    sem.is_current = True
    db.session.commit()
    flash(f'Đã đặt "{sem.display_name}" làm học kỳ hiện tại.', 'success')
    return redirect(url_for('semesters_manager'))


@admin_bp.route('/semesters/<int:sem_id>/delete', methods=['POST'], endpoint='delete_semester')
@token_required
@admin_required
def delete_semester(sem_id):
    sem = SemesterModel.query.get_or_404(sem_id)
    if GradeModel.query.filter_by(semester_id=sem_id).count() > 0:
        flash('Không thể xóa học kỳ đã có điểm!', 'danger')
        return redirect(url_for('semesters_manager'))
    db.session.delete(sem)
    db.session.commit()
    flash('Đã xóa học kỳ.', 'success')
    return redirect(url_for('semesters_manager'))


# ===================== KHOA / NGÀNH =====================
@admin_bp.route('/departments', endpoint='departments_manager')
@token_required
@admin_required
def departments_manager():
    departments = DepartmentModel.query.order_by(DepartmentModel.department_name).all()
    return render_template('departments.html', departments=departments)


@admin_bp.route('/departments/add', methods=['POST'], endpoint='add_department')
@token_required
@admin_required
def add_department():
    code = request.form.get('department_code', '').strip()
    if DepartmentModel.query.filter_by(department_code=code).first():
        flash(f'Mã khoa "{code}" đã tồn tại!', 'danger')
        return redirect(url_for('departments_manager'))
    dept = DepartmentModel(
        department_code = code,
        department_name = request.form.get('department_name', '').strip(),
    )
    db.session.add(dept)
    db.session.commit()
    flash('Đã thêm khoa mới.', 'success')
    return redirect(url_for('departments_manager'))


@admin_bp.route('/departments/<int:dept_id>/delete', methods=['POST'], endpoint='delete_department')
@token_required
@admin_required
def delete_department(dept_id):
    dept = DepartmentModel.query.get_or_404(dept_id)
    if dept.students or dept.subjects:
        flash('Không thể xóa khoa đang có sinh viên hoặc môn học!', 'danger')
        return redirect(url_for('departments_manager'))
    db.session.delete(dept)
    db.session.commit()
    flash('Đã xóa khoa.', 'success')
    return redirect(url_for('departments_manager'))


# ===================== TÀI KHOẢN =====================
@admin_bp.route('/users', endpoint='users_manager')
@token_required
@admin_required
def users_manager():
    users = UserModel.query.order_by(UserModel.username).all()
    students_no_account = (StudentModel.query
                           .filter(~StudentModel.id.in_(db.session.query(UserModel.student_id).filter(UserModel.student_id.isnot(None))))
                           .order_by(StudentModel.full_name).all())
    teachers_no_account = (TeacherModel.query
                           .filter(~TeacherModel.id.in_(db.session.query(UserModel.teacher_id).filter(UserModel.teacher_id.isnot(None))))
                           .order_by(TeacherModel.full_name).all())
    return render_template('users.html', users=users,
                           students_no_account=students_no_account,
                           teachers_no_account=teachers_no_account)


@admin_bp.route('/users/add', methods=['POST'], endpoint='add_user')
@token_required
@admin_required
def add_user():
    uname = request.form.get('username', '').strip()
    if UserModel.query.filter_by(username=uname).first():
        flash(f'Tên đăng nhập "{uname}" đã tồn tại!', 'danger')
        return redirect(url_for('users_manager'))
    role = request.form.get('role', 'student')
    user = UserModel(
        username   = uname,
        role       = role,
        student_id = request.form.get('student_id') or None if role == 'student' else None,
        teacher_id = request.form.get('teacher_id') or None if role == 'teacher' else None,
    )
    user.set_password(request.form.get('password', ''))
    db.session.add(user)
    db.session.commit()
    flash('Đã tạo tài khoản!', 'success')
    return redirect(url_for('users_manager'))


@admin_bp.route('/users/<int:user_id>/reset_password', methods=['POST'], endpoint='reset_password')
@token_required
@admin_required
def reset_password(user_id):
    user     = UserModel.query.get_or_404(user_id)
    new_pass = request.form.get('new_password', '').strip()
    if len(new_pass) < 6:
        flash('Mật khẩu mới phải có ít nhất 6 ký tự!', 'danger')
        return redirect(url_for('users_manager'))
    user.set_password(new_pass)
    user.reset_lock()
    db.session.commit()
    flash(f'Đã đặt lại mật khẩu cho {user.username}.', 'success')
    return redirect(url_for('users_manager'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'], endpoint='delete_user')
@token_required
@admin_required
def delete_user(user_id):
    user = UserModel.query.get_or_404(user_id)
    if user.username == 'admin':
        flash('Không thể xóa tài khoản admin gốc!', 'danger')
        return redirect(url_for('users_manager'))
    db.session.delete(user)
    db.session.commit()
    flash('Đã xóa tài khoản.', 'success')
    return redirect(url_for('users_manager'))


# ===================== LỚP HỌC =====================
@admin_bp.route('/classes', endpoint='classes_manager')
@token_required
@admin_required
def classes_manager():
    keyword = request.args.get('q', '').strip()
    query = ClassModel.query
    if keyword:
        like = f'%{keyword}%'
        query = query.filter(db.or_(ClassModel.class_code.ilike(like), ClassModel.class_name.ilike(like)))
    classes = query.order_by(ClassModel.class_code).all()
    departments = DepartmentModel.query.order_by(DepartmentModel.department_name).all()
    return render_template('classes.html', classes=classes, departments=departments, keyword=keyword)


@admin_bp.route('/classes/add', methods=['POST'], endpoint='add_class')
@token_required
@admin_required
def add_class():
    code = request.form.get('class_code', '').strip()
    name = request.form.get('class_name', '').strip()
    if not code or not name:
        flash('Vui lòng nhập mã lớp và tên lớp!', 'danger')
        return redirect(url_for('classes_manager'))
    if ClassModel.query.filter_by(class_code=code).first():
        flash(f'Mã lớp "{code}" đã tồn tại!', 'danger')
        return redirect(url_for('classes_manager'))
    cls = ClassModel(class_code=code, class_name=name,
                     academic_year=request.form.get('academic_year', '').strip() or None,
                     advisor_name=request.form.get('advisor_name', '').strip() or None,
                     department_id=request.form.get('department_id') or None)
    db.session.add(cls)
    db.session.commit()
    flash('Đã thêm lớp học!', 'success')
    return redirect(url_for('classes_manager'))


@admin_bp.route('/classes/<int:class_id>/edit', methods=['POST'], endpoint='edit_class')
@token_required
@admin_required
def edit_class(class_id):
    cls = ClassModel.query.get_or_404(class_id)
    cls.class_name = request.form.get('class_name', cls.class_name).strip()
    cls.academic_year = request.form.get('academic_year', '').strip() or None
    cls.advisor_name = request.form.get('advisor_name', '').strip() or None
    cls.department_id = request.form.get('department_id') or None
    db.session.commit()
    flash('Đã cập nhật lớp học!', 'success')
    return redirect(url_for('classes_manager'))


@admin_bp.route('/classes/<int:class_id>/delete', methods=['POST'], endpoint='delete_class')
@token_required
@admin_required
def delete_class(class_id):
    cls = ClassModel.query.get_or_404(class_id)
    if cls.students:
        flash('Không thể xóa lớp đang có sinh viên!', 'danger')
        return redirect(url_for('classes_manager'))
    db.session.delete(cls)
    db.session.commit()
    flash('Đã xóa lớp học!', 'success')
    return redirect(url_for('classes_manager'))


# ===================== GIẢNG VIÊN =====================
@admin_bp.route('/teachers', endpoint='teachers_manager')
@token_required
@admin_required
def teachers_manager():
    teachers = TeacherModel.query.order_by(TeacherModel.teacher_code).all()
    departments = DepartmentModel.query.order_by(DepartmentModel.department_name).all()
    return render_template('teachers.html', teachers=teachers, departments=departments)


@admin_bp.route('/teachers/add', methods=['POST'], endpoint='add_teacher')
@token_required
@admin_required
def add_teacher():
    code = request.form.get('teacher_code', '').strip()
    name = request.form.get('full_name', '').strip()
    if not code or not name:
        flash('Vui lòng nhập mã giảng viên và họ tên!', 'danger')
        return redirect(url_for('teachers_manager'))
    if TeacherModel.query.filter_by(teacher_code=code).first():
        flash(f'Mã giảng viên "{code}" đã tồn tại!', 'danger')
        return redirect(url_for('teachers_manager'))
    teacher = TeacherModel(teacher_code=code, full_name=name,
                           email=request.form.get('email', '').strip() or None,
                           phone=request.form.get('phone', '').strip() or None,
                           department_id=request.form.get('department_id') or None)
    db.session.add(teacher)
    db.session.commit()
    flash('Đã thêm giảng viên!', 'success')
    return redirect(url_for('teachers_manager'))


@admin_bp.route('/teachers/<int:teacher_id>/delete', methods=['POST'], endpoint='delete_teacher')
@token_required
@admin_required
def delete_teacher(teacher_id):
    teacher = TeacherModel.query.get_or_404(teacher_id)
    if teacher.sections:
        flash('Không thể xóa giảng viên đang được phân công lớp học phần!', 'danger')
        return redirect(url_for('teachers_manager'))
    db.session.delete(teacher)
    db.session.commit()
    flash('Đã xóa giảng viên!', 'success')
    return redirect(url_for('teachers_manager'))


# ===================== AUDIT LOG & EXPORT =====================
@admin_bp.route('/audit', endpoint='audit_log')
@token_required
@admin_required
def audit_log():
    page = request.args.get('page', 1, type=int)
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=30, error_out=False
    )
    return render_template('audit_log.html', logs=logs)


@admin_bp.route('/export', endpoint='export_excel')
@token_required
@admin_required
def export_excel():
    sem_id = request.args.get('semester_id', type=int)
    temp = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    temp.close()
    ReportService.export_students_to_excel(temp.name, semester_id=sem_id)
    return send_file(temp.name, as_attachment=True, download_name='baocao_sinhvien.xlsx')


# ===================== KHÓA ĐIỂM & PHÚC KHẢO =====================
@admin_bp.route('/appeals', endpoint='grade_appeals_manager')
@token_required
@admin_required
def grade_appeals_manager():
    from persistence.models import GradeAppealModel
    appeals = GradeAppealModel.query.order_by(GradeAppealModel.created_at.desc()).all()
    return render_template('appeals.html', appeals=appeals)


@admin_bp.route('/appeals/<int:appeal_id>/process', methods=['POST'], endpoint='process_grade_appeal')
@token_required
@admin_required
def process_grade_appeal(appeal_id):
    from persistence.models import GradeAppealModel
    appeal = GradeAppealModel.query.get_or_404(appeal_id)
    status = request.form.get('status', 'approved')
    response_text = request.form.get('response', '').strip()
    appeal.status = status
    appeal.response = response_text
    db.session.commit()
    flash('Đã xử lý đơn phúc khảo!', 'success')
    return redirect(url_for('grade_appeals_manager'))

