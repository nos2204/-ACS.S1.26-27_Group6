# student_grade_system/tests/test_services.py
import unittest
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from app import create_app
from persistence.models import (
    db, StudentModel, SubjectModel, SemesterModel,
    GradeModel, CourseSectionModel, EnrollmentModel, GradeAppealModel
)
from business.student_service import StudentService
from business.grade_service import GradeService
from business.enrollment_service import EnrollmentService
from business.semester_service import SemesterService
from business.analytics_service import AnalyticsService


class TestStudentService(unittest.TestCase):

    def setUp(self):
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'SECRET_KEY': 'test_secret_key',
            'WTF_CSRF_ENABLED': False
        })
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_score_to_gpa4(self):
        self.assertEqual(GradeService.score_to_gpa4(9.0), 4.0)
        self.assertEqual(GradeService.score_to_gpa4(8.5), 4.0)
        self.assertEqual(GradeService.score_to_gpa4(7.5), 3.0)
        self.assertEqual(GradeService.score_to_gpa4(6.0), 2.0)
        self.assertEqual(GradeService.score_to_gpa4(4.5), 1.0)
        self.assertEqual(GradeService.score_to_gpa4(3.0), 0.0)

        # Backward compatibility test
        self.assertEqual(StudentService.score_to_gpa4(8.5), 4.0)

    def test_classify_academic(self):
        self.assertEqual(GradeService.classify_academic(3.8), 'Xuất sắc')
        self.assertEqual(GradeService.classify_academic(3.4), 'Giỏi')
        self.assertEqual(GradeService.classify_academic(2.8), 'Khá')
        self.assertEqual(GradeService.classify_academic(2.2), 'Trung bình')
        self.assertEqual(GradeService.classify_academic(1.5), 'Yếu')
        self.assertEqual(GradeService.classify_academic(0.5), 'Kém')

    def test_calculate_student_gpa(self):
        sem = SemesterModel.query.first()
        if not sem:
            sem = SemesterModel(name='Học kỳ 1', academic_year='2024-2025', is_current=True)
            db.session.add(sem)
            db.session.flush()

        student = StudentModel(student_code='SV999', full_name='Nguyễn Văn Test')
        subj1 = SubjectModel(subject_code='MATH101', subject_name='Toán Cao Cấp', credits=3)
        subj2 = SubjectModel(subject_code='PROG101', subject_name='Lập Trình Python', credits=4)
        db.session.add_all([student, subj1, subj2])
        db.session.flush()

        g1 = GradeModel(student_id=student.id, subject_id=subj1.id, semester_id=sem.id, progress_grade=8.5, exam_grade=8.5)
        g2 = GradeModel(student_id=student.id, subject_id=subj2.id, semester_id=sem.id, progress_grade=7.0, exam_grade=7.0)
        db.session.add_all([g1, g2])
        db.session.commit()

        gpa = GradeService.calculate_student_gpa(student.id)
        self.assertEqual(gpa, 3.43)

        # Backward compatibility test
        self.assertEqual(StudentService.calculate_student_gpa(student.id), 3.43)

    def test_dynamic_grade_weighting(self):
        subj = SubjectModel(subject_code='LAB101', subject_name='Thực hành', credits=2, progress_weight=0.3, exam_weight=0.7)
        student = StudentModel(student_code='SV998', full_name='Trần Thị Test')
        sem = SemesterModel.query.first()
        db.session.add_all([subj, student])
        db.session.flush()

        g = GradeModel(student_id=student.id, subject_id=subj.id, semester_id=sem.id, progress_grade=10.0, exam_grade=5.0)
        db.session.add(g)
        db.session.commit()

        self.assertEqual(g.final_grade, 6.5)

    def test_check_prerequisites_met(self):
        sub_base = SubjectModel(subject_code='BAS101', subject_name='Nhập môn Tin học', credits=3)
        sub_adv = SubjectModel(subject_code='ADV101', subject_name='Lập trình Nâng cao', credits=3)
        sub_adv.prerequisites.append(sub_base)

        student = StudentModel(student_code='SV997', full_name='Lê Văn Test')
        sem = SemesterModel.query.first()
        db.session.add_all([sub_base, sub_adv, student])
        db.session.commit()

        passed, missing = EnrollmentService.check_prerequisites_met(student.id, sub_adv)
        self.assertFalse(passed)
        self.assertIn('Nhập môn Tin học', missing)

        g = GradeModel(student_id=student.id, subject_id=sub_base.id, semester_id=sem.id, progress_grade=7.0, exam_grade=7.0)
        db.session.add(g)
        db.session.commit()

        passed, missing = EnrollmentService.check_prerequisites_met(student.id, sub_adv)
        self.assertTrue(passed)
        self.assertEqual(len(missing), 0)

    def test_check_schedule_conflict(self):
        sem = SemesterModel.query.first()
        subj1 = SubjectModel(subject_code='S1', subject_name='Môn 1', credits=3)
        subj2 = SubjectModel(subject_code='S2', subject_name='Môn 2', credits=3)
        db.session.add_all([subj1, subj2])
        db.session.flush()

        sec1 = CourseSectionModel(section_code='HP01', subject_id=subj1.id, semester_id=sem.id, schedule='Thứ 2 (07:00-09:00)')
        sec2 = CourseSectionModel(section_code='HP02', subject_id=subj2.id, semester_id=sem.id, schedule='Thứ 2 (08:30-10:30)')
        student = StudentModel(student_code='SV996', full_name='Phạm Văn Test')
        db.session.add_all([sec1, sec2, student])
        db.session.flush()

        enr = EnrollmentModel(student_id=student.id, section_id=sec1.id, status='registered')
        db.session.add(enr)
        db.session.commit()

        is_conflict, msg = EnrollmentService.check_schedule_conflict(student.id, sec2)
        self.assertTrue(is_conflict)
        self.assertIn('Trùng lịch học với lớp HP01', msg)

    def test_create_grade_appeal(self):
        sem = SemesterModel.query.first()
        subj = SubjectModel(subject_code='S3', subject_name='Môn 3', credits=3)
        student = StudentModel(student_code='SV995', full_name='Hoàng Văn Test')
        db.session.add_all([subj, student])
        db.session.commit()

        ok, msg = GradeService.create_grade_appeal(student.id, subj.id, sem.id, 'Chấm sót câu 3 phần tự luận.')
        self.assertTrue(ok)

        ok2, msg2 = GradeService.create_grade_appeal(student.id, subj.id, sem.id, 'Nộp thêm lý do.')
        self.assertFalse(ok2)

    def test_analytics_dashboard_stats(self):
        stats = AnalyticsService.get_dashboard_stats()
        self.assertIn('total', stats)
        self.assertIn('gioi', stats)
        self.assertIn('kha', stats)
        self.assertIn('tb', stats)
        self.assertIn('yeu', stats)

    def test_semester_service(self):
        sem = SemesterService.get_current_semester()
        self.assertIsNotNone(sem)
        all_sems = SemesterService.get_all_semesters()
        self.assertGreaterEqual(len(all_sems), 1)


if __name__ == '__main__':
    unittest.main()
