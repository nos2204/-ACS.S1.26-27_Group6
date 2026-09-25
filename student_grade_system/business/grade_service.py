# business/grade_service.py
from datetime import datetime
from persistence.models import (
    db, StudentModel, GradeModel, SubjectModel, SemesterModel,
    AuditLog, EnrollmentModel, GradeAppealModel
)

# Ngưỡng cảnh báo điểm tích lũy (thang 4)
GPA_WARNING_THRESHOLD = 1.0   # Dưới 1.0 / 4 → cảnh báo nghiêm trọng
GPA_LOW_THRESHOLD     = 2.0   # Dưới 2.0 / 4 → cảnh báo học lực yếu


class GradeService:
    """Nghiệp vụ quản lý điểm số, tính GPA, xếp loại học lực, cảnh báo học vụ và phúc khảo."""

    @staticmethod
    def score_to_gpa4(score: float) -> float:
        """Chuyển đổi điểm thang 10 sang thang 4 (GPA)."""
        if score >= 8.5:
            return 4.0
        if score >= 7.0:
            return 3.0
        if score >= 5.5:
            return 2.0
        if score >= 4.0:
            return 1.0
        return 0.0

    @staticmethod
    def classify_academic(gpa: float) -> str:
        """Phân loại học lực theo thang GPA 4."""
        if gpa >= 3.6:
            return 'Xuất sắc'
        if gpa >= 3.2:
            return 'Giỏi'
        if gpa >= 2.5:
            return 'Khá'
        if gpa >= 2.0:
            return 'Trung bình'
        if gpa >= 1.0:
            return 'Yếu'
        return 'Kém'

    @staticmethod
    def calculate_student_gpa(student_id: int, semester_id: int = None) -> float:
        """
        Tính GPA thang 4 dựa trên điểm tích lũy có trọng số tín chỉ.
        Hỗ trợ tính theo từng học kỳ hoặc toàn khóa (tích lũy).
        """
        query = GradeModel.query.filter_by(student_id=student_id)
        if semester_id:
            query = query.filter_by(semester_id=semester_id)
        grades = query.all()
        if not grades:
            return 0.0

        total_points = 0.0
        total_credits = 0
        for g in grades:
            credits = g.subject.credits if g.subject else 0
            if credits > 0:
                gpa4 = GradeService.score_to_gpa4(g.final_grade)
                total_points += gpa4 * credits
                total_credits += credits

        return round(total_points / total_credits, 2) if total_credits > 0 else 0.0

    @staticmethod
    def calculate_student_avg10(student_id: int, semester_id: int = None) -> float:
        """Tính điểm trung bình thang 10 có trọng số tín chỉ."""
        query = GradeModel.query.filter_by(student_id=student_id)
        if semester_id:
            query = query.filter_by(semester_id=semester_id)
        grades = query.all()
        if not grades:
            return 0.0

        total_points = 0.0
        total_credits = 0
        for g in grades:
            credits = g.subject.credits if g.subject else 0
            if credits > 0:
                total_points += g.final_grade * credits
                total_credits += credits

        return round(total_points / total_credits, 2) if total_credits > 0 else 0.0

    @staticmethod
    def get_student_warnings(student_id: int, semester_id: int = None) -> list:
        """
        Kiểm tra và trả về danh sách cảnh báo học vụ cho sinh viên:
        - Môn học chưa hoàn thành (chưa đạt / rớt môn)
        - Môn học đã đăng ký nhưng chưa có điểm
        - Điểm tích lũy (GPA) thấp
        """
        warnings = []

        # 1. Kiểm tra các môn chưa hoàn thành (điểm < 4.0 = Rớt)
        query = GradeModel.query.filter_by(student_id=student_id)
        if semester_id:
            query = query.filter_by(semester_id=semester_id)
        grades = query.all()

        failed_subjects = [g for g in grades if not g.is_passed]
        if failed_subjects:
            mon_list = ', '.join(
                f"{g.subject.subject_name if g.subject else g.subject_id} ({g.final_grade:.1f})"
                for g in failed_subjects
            )
            warnings.append({
                'level': 'danger',
                'icon': 'bi-x-circle-fill',
                'message': f"Chưa hoàn thành {len(failed_subjects)} môn học: {mon_list}. Cần học lại hoặc thi lại."
            })

        # 2. Kiểm tra môn đăng ký nhưng chưa có điểm
        enrollments = EnrollmentModel.query.filter_by(student_id=student_id, status='registered').all()
        graded_subject_ids = {g.subject_id for g in grades}
        missing_grades = []
        for enr in enrollments:
            subj = enr.section.subject if enr.section else None
            if subj and subj.id not in graded_subject_ids:
                missing_grades.append(subj.subject_name)
        if missing_grades:
            mon_list = ', '.join(missing_grades)
            warnings.append({
                'level': 'warning',
                'icon': 'bi-hourglass-split',
                'message': f"Chưa có điểm cho {len(missing_grades)} môn đã đăng ký: {mon_list}."
            })

        # 3. Kiểm tra GPA tích lũy
        gpa = GradeService.calculate_student_gpa(student_id)
        if 0 < gpa < GPA_WARNING_THRESHOLD:
            warnings.append({
                'level': 'danger',
                'icon': 'bi-exclamation-octagon-fill',
                'message': f"Điểm tích lũy rất thấp (GPA = {gpa:.2f}/4.0). Có nguy cơ bị buộc thôi học!"
            })
        elif 0 < gpa < GPA_LOW_THRESHOLD:
            warnings.append({
                'level': 'warning',
                'icon': 'bi-exclamation-triangle-fill',
                'message': f"Điểm tích lũy chưa đủ (GPA = {gpa:.2f}/4.0). Cần cải thiện kết quả học tập."
            })

        return warnings

    @staticmethod
    def upsert_grade(student_id: int, subject_id: int, semester_id: int,
                     progress_grade: float, exam_grade: float, actor: str = 'system') -> GradeModel:
        """Nhập mới hoặc cập nhật điểm học phần của sinh viên."""
        from business.student_service import StudentService

        grade = GradeModel.query.filter_by(
            student_id=student_id,
            subject_id=subject_id,
            semester_id=semester_id
        ).first()

        subject = SubjectModel.query.get(subject_id)
        student = StudentModel.query.get(student_id)
        sem = SemesterModel.query.get(semester_id) if semester_id else None
        sem_name = sem.display_name if sem else '?'

        if grade:
            old_detail = f"QT={grade.progress_grade}, Thi={grade.exam_grade}"
            grade.progress_grade = progress_grade
            grade.exam_grade = exam_grade
            grade.updated_at = datetime.utcnow()
            action = 'update_grade'
        else:
            old_detail = 'mới'
            grade = GradeModel(
                student_id=student_id,
                subject_id=subject_id,
                semester_id=semester_id,
                progress_grade=progress_grade,
                exam_grade=exam_grade
            )
            db.session.add(grade)
            action = 'insert_grade'

        db.session.commit()
        StudentService.update_student_stats(student_id)

        stu_code = student.student_code if student else str(student_id)
        sub_code = subject.subject_code if subject else str(subject_id)
        log = AuditLog(
            actor=actor,
            action=action,
            target=f"SV={stu_code} | Môn={sub_code} | Kỳ={sem_name}",
            detail=f"Cũ: {old_detail} → Mới: QT={progress_grade}, Thi={exam_grade}"
        )
        db.session.add(log)
        db.session.commit()
        return grade

    @staticmethod
    def create_grade_appeal(student_id: int, subject_id: int, semester_id: int, reason: str):
        """Tạo đơn khiếu nại/phúc khảo điểm."""
        existing = GradeAppealModel.query.filter_by(
            student_id=student_id,
            subject_id=subject_id,
            semester_id=semester_id,
            status='pending'
        ).first()

        if existing:
            return False, 'Bạn đã có một yêu cầu phúc khảo đang chờ xử lý cho môn học này!'

        appeal = GradeAppealModel(
            student_id=student_id,
            subject_id=subject_id,
            semester_id=semester_id,
            reason=reason.strip(),
            status='pending'
        )
        db.session.add(appeal)
        db.session.commit()
        return True, 'Đã gửi yêu cầu phúc khảo thành công!'
