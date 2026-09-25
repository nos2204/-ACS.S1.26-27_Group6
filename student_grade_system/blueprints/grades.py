# student_grade_system/blueprints/grades.py
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, Response
from persistence.models import (db, StudentModel, GradeModel, SubjectModel, SemesterModel)
from business.grade_service import GradeService
from business.report_service import ReportService
from gateway import token_required, admin_required, admin_or_self_required

grades_bp = Blueprint('grades', __name__)


@grades_bp.route('/students/<int:student_id>/grades', methods=['GET', 'POST'], endpoint='manage_grades')
@token_required
@admin_or_self_required
def manage_grades(student_id):
    student   = StudentModel.query.get_or_404(student_id)
    subjects  = SubjectModel.query.order_by(SubjectModel.subject_name).all()
    semesters = SemesterModel.query.order_by(
        SemesterModel.academic_year.desc(), SemesterModel.name
    ).all()

    sel_sem_id = request.args.get('semester_id', type=int)
    if not sel_sem_id:
        current = SemesterModel.query.filter_by(is_current=True).first()
        sel_sem_id = current.id if current else (semesters[0].id if semesters else None)

    grades = {}
    if sel_sem_id:
        grades = {g.subject_id: g for g in
                  GradeModel.query.filter_by(student_id=student_id,
                                             semester_id=sel_sem_id).all()}

    if request.method == 'POST' and session.get('role') == 'admin':
        if not sel_sem_id:
            flash('Không có học kỳ nào để lưu điểm!', 'danger')
            return redirect(url_for('manage_grades', student_id=student_id))

        for subject in subjects:
            pg_key = f'progress_{subject.id}'
            eg_key = f'exam_{subject.id}'
            if pg_key in request.form and eg_key in request.form:
                try:
                    pg = float(request.form[pg_key])
                    eg = float(request.form[eg_key])
                    if 0 <= pg <= 10 and 0 <= eg <= 10:
                        GradeService.upsert_grade(
                            student_id, subject.id, sel_sem_id,
                            pg, eg, actor=session['username']
                        )
                except ValueError:
                    pass
        flash('Đã cập nhật điểm và tính lại Điểm tích lũy!', 'success')
        return redirect(url_for('manage_grades', student_id=student_id,
                                semester_id=sel_sem_id))

    sem_gpa     = GradeService.calculate_student_gpa(student_id, sel_sem_id) if sel_sem_id else 0
    sem_avg10   = GradeService.calculate_student_avg10(student_id, sel_sem_id) if sel_sem_id else 0
    total_avg10 = GradeService.calculate_student_avg10(student_id)
    student     = StudentModel.query.get(student_id)
    warnings    = GradeService.get_student_warnings(student_id, sel_sem_id)
    return render_template('grades.html',
                           student=student, subjects=subjects,
                           grades=grades, semesters=semesters,
                           sel_sem_id=sel_sem_id,
                           sem_gpa=sem_gpa, sem_avg10=sem_avg10,
                           total_avg10=total_avg10,
                           warnings=warnings)


@grades_bp.route('/grades/import', methods=['GET', 'POST'], endpoint='import_grades')
@token_required
@admin_required
def import_grades():
    semesters = SemesterModel.query.order_by(
        SemesterModel.academic_year.desc(), SemesterModel.name
    ).all()

    if request.method == 'POST':
        f   = request.files.get('csv_file')
        sid = request.form.get('semester_id', type=int)
        if not f or not f.filename.endswith('.csv') or not sid:
            flash('Vui lòng chọn file CSV và học kỳ.', 'danger')
            return redirect(url_for('import_grades'))

        updated, errors = ReportService.import_grades_from_csv(
            f.stream, semester_id=sid, actor=session['username']
        )
        flash(f'Import điểm hoàn tất: cập nhật {updated} bản ghi.', 'success')
        for err in errors[:10]:
            flash(err, 'warning')
        return redirect(url_for('students_manager'))

    return render_template('import_grades.html', semesters=semesters)


@grades_bp.route('/students/<int:student_id>/transcript.pdf', endpoint='export_transcript_pdf')
@token_required
@admin_or_self_required
def export_transcript_pdf(student_id):
    sem_id = request.args.get('semester_id', type=int)
    try:
        pdf_bytes = ReportService.export_transcript_pdf(student_id, sem_id)
    except RuntimeError as e:
        flash(str(e), 'danger')
        return redirect(url_for('manage_grades', student_id=student_id))

    student = StudentModel.query.get(student_id)
    filename = f"bangdiem_{student.student_code}.pdf"
    return Response(pdf_bytes, mimetype='application/pdf',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})


@grades_bp.route('/grades/appeal', methods=['POST'], endpoint='submit_grade_appeal')
@token_required
def submit_grade_appeal():
    if session.get('role') != 'student':
        from flask import abort
        abort(403)
    from persistence.models import UserModel
    user = UserModel.query.filter_by(username=session.get('username')).first()
    if not user or not user.student_id:
        flash('Tài khoản chưa liên kết sinh viên!', 'danger')
        return redirect(url_for('dashboard'))

    subject_id = request.form.get('subject_id', type=int)
    semester_id = request.form.get('semester_id', type=int)
    reason = request.form.get('reason', '').strip()

    if not subject_id or not semester_id or not reason:
        flash('Vui lòng điền đầy đủ lý do phúc khảo!', 'danger')
        return redirect(url_for('manage_grades', student_id=user.student_id))

    ok, msg = GradeService.create_grade_appeal(user.student_id, subject_id, semester_id, reason)
    flash(msg, 'success' if ok else 'warning')
    return redirect(url_for('manage_grades', student_id=user.student_id, semester_id=semester_id))
