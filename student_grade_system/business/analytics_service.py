# business/analytics_service.py
from persistence.models import (
    db, StudentModel, GradeModel, SubjectModel, SemesterModel,
    UserModel, DepartmentModel, ClassModel, TeacherModel,
    CourseSectionModel, EnrollmentModel
)
from business.grade_service import GPA_LOW_THRESHOLD


class AnalyticsService:
    """Nghiệp vụ tổng hợp số liệu thống kê, phân tích phổ điểm và dashboard."""

    @staticmethod
    def get_dashboard_stats() -> dict:
        """Tổng hợp toàn bộ chỉ số thống kê trên Dashboard."""
        total = StudentModel.query.count()
        gioi = StudentModel.query.filter(StudentModel.academic_rank.in_(['Giỏi', 'Xuất sắc'])).count()
        kha = StudentModel.query.filter_by(academic_rank='Khá').count()
        tb = StudentModel.query.filter_by(academic_rank='Trung bình').count()
        yeu = StudentModel.query.filter(StudentModel.academic_rank.in_(['Yếu', 'Kém'])).count()
        nam = StudentModel.query.filter_by(gender='Nam').count()
        nu = StudentModel.query.filter_by(gender='Nữ').count()

        total_subjects = SubjectModel.query.count()
        total_departments = DepartmentModel.query.count()
        total_semesters = SemesterModel.query.count()
        total_users = UserModel.query.count()
        total_classes = ClassModel.query.count()
        total_teachers = TeacherModel.query.count()
        total_sections = CourseSectionModel.query.count()
        total_enrollments = EnrollmentModel.query.filter_by(status='registered').count()

        no_account = StudentModel.query.filter(
            ~StudentModel.id.in_(
                db.session.query(UserModel.student_id).filter(UserModel.student_id.isnot(None))
            )
        ).count()

        no_grade = StudentModel.query.filter(
            ~StudentModel.id.in_(db.session.query(GradeModel.student_id))
        ).count()

        warning_students = StudentModel.query.filter(
            StudentModel.gpa > 0,
            StudentModel.gpa < GPA_LOW_THRESHOLD
        ).count()

        top5 = (StudentModel.query.filter(StudentModel.gpa > 0)
                .order_by(StudentModel.gpa.desc())
                .limit(5)
                .all())

        current_sem = SemesterModel.query.filter_by(is_current=True).first()

        return dict(
            total=total, gioi=gioi, kha=kha, tb=tb, yeu=yeu,
            nam=nam, nu=nu, top5=top5, current_sem=current_sem,
            total_subjects=total_subjects, total_departments=total_departments,
            total_semesters=total_semesters, total_users=total_users,
            total_classes=total_classes, total_teachers=total_teachers,
            total_sections=total_sections, total_enrollments=total_enrollments,
            no_account=no_account, no_grade=no_grade,
            warning_students=warning_students
        )

    @staticmethod
    def get_grade_distribution(semester_id: int = None, subject_id: int = None) -> dict:
        """Phân bố điểm chữ (A, B, C, D, F) theo học kỳ hoặc môn học."""
        query = GradeModel.query
        if semester_id:
            query = query.filter_by(semester_id=semester_id)
        if subject_id:
            query = query.filter_by(subject_id=subject_id)

        grades = query.all()
        distribution = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'F': 0}
        for g in grades:
            distribution[g.letter_grade] = distribution.get(g.letter_grade, 0) + 1

        return distribution
