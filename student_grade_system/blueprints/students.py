# student_grade_system/blueprints/students.py
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from persistence.models import (db, StudentModel, GradeModel, SubjectModel, SemesterModel,
                                 DepartmentModel, ClassModel, UserModel, EnrollmentModel)
from business.student_service import StudentService
from business.report_service import ReportService
from gateway import token_required, admin_required, admin_or_self_required

students_bp = Blueprint('students', __name__)


@students_bp.route('/students', endpoint='students_manager')
@token_required
def students_manager():
    keyword       = request.args.get('q', '').strip()
    gender        = request.args.get('gender', '')
    rank          = request.args.get('rank', '')
    department_id = request.args.get('department_id', '')
    class_id      = request.args.get('class_id', '')
    page          = request.args.get('page', 1, type=int)

    students, total_pages, total = StudentService.search_students(
        keyword=keyword, gender=gender, rank=rank,
        department_id=department_id, class_id=class_id, page=page
    )
    departments = DepartmentModel.query.order_by(DepartmentModel.department_name).all()
    classes = ClassModel.query.order_by(ClassModel.class_code).all()
    return render_template(
        'students.html',
        students=students, keyword=keyword, gender=gender,
        rank=rank, department_id=department_id, class_id=class_id,
        page=page, total_pages=total_pages, total=total,
        departments=departments, classes=classes,
    )


@students_bp.route('/students/<int:student_id>', endpoint='student_detail')
@token_required
@admin_or_self_required
def student_detail(student_id):
    student = StudentModel.query.get_or_404(student_id)
    grades = (GradeModel.query.filter_by(student_id=student_id)
              .join(SubjectModel).join(SemesterModel)
              .order_by(SemesterModel.academic_year.desc(), SemesterModel.name, SubjectModel.subject_name)
              .all())
    user = UserModel.query.filter_by(student_id=student_id).first()
    enrollments = EnrollmentModel.query.filter_by(student_id=student_id).order_by(EnrollmentModel.registered_at.desc()).all()
    return render_template('student_detail.html', student=student, grades=grades, user=user, enrollments=enrollments)


@students_bp.route('/students/add', methods=['GET', 'POST'], endpoint='add_student')
@token_required
@admin_required
def add_student():
    if request.method == 'POST':
        code = request.form.get('student_code', '').strip()
        if StudentModel.query.filter_by(student_code=code).first():
            flash(f'MSSV "{code}" đã tồn tại!', 'danger')
            return redirect(url_for('add_student'))

        dob_str = request.form.get('date_of_birth', '')
        dob     = datetime.strptime(dob_str, '%Y-%m-%d').date() if dob_str else None
        dept_id = request.form.get('department_id') or None
        class_id = request.form.get('class_id') or None

        student = StudentModel(
            student_code  = code,
            full_name     = request.form.get('full_name', '').strip(),
            gender        = request.form.get('gender', 'Nam'),
            email         = request.form.get('email', '').strip() or None,
            phone         = request.form.get('phone', '').strip() or None,
            class_name    = request.form.get('class_name', '').strip() or None,
            class_id      = class_id,
            address       = request.form.get('address', '').strip() or None,
            date_of_birth = dob,
            department_id = dept_id,
        )
        db.session.add(student)
        db.session.commit()
        flash(f'Đã thêm sinh viên {student.full_name} thành công!', 'success')
        return redirect(url_for('students_manager'))

    departments = DepartmentModel.query.order_by(DepartmentModel.department_name).all()
    classes = ClassModel.query.order_by(ClassModel.class_code).all()
    return render_template('student_form.html', student=None, action='add',
                           departments=departments, classes=classes)


@students_bp.route('/students/<int:student_id>/edit', methods=['GET', 'POST'], endpoint='edit_student')
@token_required
@admin_required
def edit_student(student_id):
    student = StudentModel.query.get_or_404(student_id)
    if request.method == 'POST':
        code = request.form.get('student_code', '').strip()
        dup  = StudentModel.query.filter(
            StudentModel.student_code == code,
            StudentModel.id != student_id
        ).first()
        if dup:
            flash(f'MSSV "{code}" đã tồn tại!', 'danger')
            return redirect(url_for('edit_student', student_id=student_id))

        dob_str = request.form.get('date_of_birth', '')
        dob     = datetime.strptime(dob_str, '%Y-%m-%d').date() if dob_str else None
        dept_id = request.form.get('department_id') or None
        class_id = request.form.get('class_id') or None

        student.student_code  = code
        student.full_name     = request.form.get('full_name', '').strip()
        student.gender        = request.form.get('gender', 'Nam')
        student.email         = request.form.get('email', '').strip() or None
        student.phone         = request.form.get('phone', '').strip() or None
        student.class_name    = request.form.get('class_name', '').strip() or None
        student.class_id      = class_id
        student.address       = request.form.get('address', '').strip() or None
        student.date_of_birth = dob
        student.department_id = dept_id
        db.session.commit()
        flash('Cập nhật thông tin sinh viên thành công!', 'success')
        return redirect(url_for('students_manager'))

    departments = DepartmentModel.query.order_by(DepartmentModel.department_name).all()
    classes = ClassModel.query.order_by(ClassModel.class_code).all()
    return render_template('student_form.html', student=student, action='edit',
                           departments=departments, classes=classes)


@students_bp.route('/students/<int:student_id>/delete', methods=['POST'], endpoint='delete_student')
@token_required
@admin_required
def delete_student(student_id):
    student = StudentModel.query.get_or_404(student_id)
    name    = student.full_name
    db.session.delete(student)
    db.session.commit()
    flash(f'Đã xóa sinh viên {name}.', 'success')
    return redirect(url_for('students_manager'))


@students_bp.route('/students/import', methods=['GET', 'POST'], endpoint='import_students')
@token_required
@admin_required
def import_students():
    if request.method == 'POST':
        f = request.files.get('csv_file')
        if not f or not f.filename.endswith('.csv'):
            flash('Vui lòng chọn file CSV hợp lệ.', 'danger')
            return redirect(url_for('import_students'))

        added, skipped, errors = ReportService.import_students_from_csv(
            f.stream, actor=session['username']
        )
        flash(f'Import hoàn tất: thêm mới {added}, bỏ qua {skipped} (trùng MSSV).', 'success')
        if errors:
            for err in errors[:10]:
                flash(err, 'warning')
        return redirect(url_for('students_manager'))

    return render_template('import_students.html')


@students_bp.route('/student/degree-progress', endpoint='student_degree_progress')
@token_required
def student_degree_progress():
    """Degree Progress Tracker - Theo dõi tiến độ học tập"""
    if session.get('role') != 'student':
        flash('Bạn không có quyền truy cập trang này!', 'danger')
        return redirect(url_for('dashboard'))
    
    from persistence.models import UserModel
    user = UserModel.query.filter_by(username=session.get('username')).first()
    
    if not user or not user.student_id:
        flash('Tài khoản sinh viên chưa được liên kết!', 'warning')
        return redirect(url_for('dashboard'))
    
    student = StudentModel.query.get_or_404(user.student_id)
    
    # Lấy tất cả điểm của sinh viên
    all_grades = GradeModel.query.filter_by(student_id=student.id).all()
    
    # Xử lý quy chế học lại: lấy điểm cao nhất cho mỗi môn
    subject_best_grades = {}
    for grade in all_grades:
        if grade.subject_id not in subject_best_grades:
            subject_best_grades[grade.subject_id] = grade
        else:
            # So sánh điểm tổng, lấy điểm cao nhất
            if grade.final_grade > subject_best_grades[grade.subject_id].final_grade:
                subject_best_grades[grade.subject_id] = grade
    
    best_grades = list(subject_best_grades.values())
    
    # Phân loại theo khối kiến thức
    categories = {
        'general': {'name': 'Đại cương', 'credits_earned': 0, 'credits_required': 30, 'subjects': []},
        'foundation': {'name': 'Cơ sở ngành', 'credits_earned': 0, 'credits_required': 45, 'subjects': []},
        'major': {'name': 'Chuyên ngành', 'credits_earned': 0, 'credits_required': 60, 'subjects': []}
    }
    
    total_credits_earned = 0
    total_credits_required = 135  # Tổng số tín chỉ yêu cầu
    failed_subjects = []
    
    for grade in best_grades:
        subject = grade.subject
        category_key = subject.category if subject.category in categories else 'general'
        
        if grade.is_passed:
            categories[category_key]['credits_earned'] += subject.credits
            categories[category_key]['subjects'].append({
                'subject': subject,
                'grade': grade,
                'status': 'passed'
            })
            total_credits_earned += subject.credits
        else:
            categories[category_key]['subjects'].append({
                'subject': subject,
                'grade': grade,
                'status': 'failed'
            })
            failed_subjects.append(subject)
    
    # Tính GPA (chỉ tính môn đã qua)
    total_grade_points = sum(g.grade_point_4 * g.subject.credits for g in best_grades if g.is_passed)
    total_credits_for_gpa = sum(g.subject.credits for g in best_grades if g.is_passed)
    gpa = round(total_grade_points / total_credits_for_gpa, 2) if total_credits_for_gpa > 0 else 0.0
    
    # Dự báo tốt nghiệp
    can_graduate = (
        total_credits_earned >= total_credits_required and
        gpa >= 2.0 and
        len(failed_subjects) == 0
    )
    
    return render_template('student_degree_progress.html',
                         student=student,
                         categories=categories,
                         total_credits_earned=total_credits_earned,
                         total_credits_required=total_credits_required,
                         gpa=gpa,
                         failed_subjects=failed_subjects,
                         can_graduate=can_graduate)
