# business/student_service.py
from persistence.models import db, StudentModel
from business.grade_service import GradeService
from business.enrollment_service import EnrollmentService
from business.semester_service import SemesterService
from business.report_service import ReportService
from business.analytics_service import AnalyticsService

# Re-export thresholds for backward compatibility
from business.grade_service import GPA_WARNING_THRESHOLD, GPA_LOW_THRESHOLD


class StudentService:
    """Nghiệp vụ quản lý hồ sơ sinh viên, tìm kiếm, phân trang và cập nhật học lực."""

    @staticmethod
    def update_student_stats(student_id: int):
        """Tính lại GPA và cập nhật xếp loại học lực cho sinh viên."""
        student = StudentModel.query.get(student_id)
        if student:
            student.gpa = GradeService.calculate_student_gpa(student_id)
            student.academic_rank = GradeService.classify_academic(student.gpa)
            db.session.commit()

    @staticmethod
    def search_students(keyword: str = '', gender: str = '', rank: str = '',
                        department_id: str = '', class_id: str = '',
                        page: int = 1, per_page: int = 15):
        """Tìm kiếm, lọc và phân trang danh sách sinh viên."""
        query = StudentModel.query
        if keyword:
            like = f'%{keyword}%'
            query = query.filter(
                db.or_(
                    StudentModel.full_name.ilike(like),
                    StudentModel.student_code.ilike(like),
                    StudentModel.class_name.ilike(like),
                )
            )
        if gender:
            query = query.filter_by(gender=gender)
        if rank:
            query = query.filter_by(academic_rank=rank)
        if department_id:
            query = query.filter_by(department_id=department_id)
        if class_id:
            query = query.filter_by(class_id=class_id)

        total = query.count()
        students = query.order_by(StudentModel.full_name).paginate(
            page=page, per_page=per_page, error_out=False
        )
        return students.items, students.pages, total

    @staticmethod
    def get_student_by_code(student_code: str):
        """Tìm sinh viên theo mã số sinh viên."""
        return StudentModel.query.filter_by(student_code=student_code.strip()).first()

    # -------------------------------------------------------------------------
    # Backward Compatibility Delegations (Giữ tương thích cho các lệnh gọi cũ)
    # -------------------------------------------------------------------------
    @staticmethod
    def score_to_gpa4(score):
        return GradeService.score_to_gpa4(score)

    @staticmethod
    def classify_academic(gpa):
        return GradeService.classify_academic(gpa)

    @staticmethod
    def calculate_student_gpa(student_id, semester_id=None):
        return GradeService.calculate_student_gpa(student_id, semester_id)

    @staticmethod
    def calculate_student_avg10(student_id, semester_id=None):
        return GradeService.calculate_student_avg10(student_id, semester_id)

    @staticmethod
    def get_student_warnings(student_id, semester_id=None):
        return GradeService.get_student_warnings(student_id, semester_id)

    @staticmethod
    def upsert_grade(student_id, subject_id, semester_id, progress_grade, exam_grade, actor='system'):
        return GradeService.upsert_grade(student_id, subject_id, semester_id, progress_grade, exam_grade, actor)

    @staticmethod
    def create_grade_appeal(student_id, subject_id, semester_id, reason):
        return GradeService.create_grade_appeal(student_id, subject_id, semester_id, reason)

    @staticmethod
    def check_schedule_conflict(student_id, new_section):
        return EnrollmentService.check_schedule_conflict(student_id, new_section)

    @staticmethod
    def check_prerequisites_met(student_id, subject):
        return EnrollmentService.check_prerequisites_met(student_id, subject)

    @staticmethod
    def import_students_from_csv(file_stream, actor='admin'):
        return ReportService.import_students_from_csv(file_stream, actor)

    @staticmethod
    def import_grades_from_csv(file_stream, semester_id, actor='admin'):
        return ReportService.import_grades_from_csv(file_stream, semester_id, actor)

    @staticmethod
    def export_students_to_excel(file_path, semester_id=None):
        return ReportService.export_students_to_excel(file_path, semester_id)

    @staticmethod
    def export_transcript_pdf(student_id, semester_id=None):
        return ReportService.export_transcript_pdf(student_id, semester_id)

    @staticmethod
    def get_dashboard_stats():
        return AnalyticsService.get_dashboard_stats()
