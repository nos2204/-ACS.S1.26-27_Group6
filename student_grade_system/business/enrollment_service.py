# business/enrollment_service.py
from persistence.models import (
    db, GradeModel, CourseSectionModel, EnrollmentModel, SubjectModel
)


class EnrollmentService:
    """Nghiệp vụ đăng ký tín chỉ, kiểm tra môn tiên quyết và xung đột lịch học."""

    @staticmethod
    def check_schedule_conflict(student_id: int, new_section: CourseSectionModel):
        """
        Kiểm tra xung đột lịch học giữa lớp học phần mới đăng ký và các lớp đã đăng ký của sinh viên trong cùng kỳ.
        Trả về: (is_conflict: bool, conflict_message: str|None)
        """
        from blueprints.timetable import parse_schedule_text, time_to_minutes

        new_parsed = parse_schedule_text(new_section.schedule or '')
        if not new_parsed or not new_parsed.get('weekday'):
            return False, None

        new_day = new_parsed['weekday']
        new_start = time_to_minutes(new_parsed['start_time'])
        new_end = time_to_minutes(new_parsed['end_time'])

        enrollments = EnrollmentModel.query.filter_by(
            student_id=student_id, status='registered'
        ).join(CourseSectionModel).filter(
            CourseSectionModel.semester_id == new_section.semester_id
        ).all()

        for e in enrollments:
            sec = e.section
            if not sec or sec.id == new_section.id:
                continue
            parsed = parse_schedule_text(sec.schedule or '')
            if not parsed or not parsed.get('weekday'):
                continue

            if parsed['weekday'] == new_day:
                start_m = time_to_minutes(parsed['start_time'])
                end_m = time_to_minutes(parsed['end_time'])

                if (new_start < end_m) and (new_end > start_m):
                    subj_name = sec.subject.subject_name if sec.subject else sec.section_code
                    msg = f"Trùng lịch học với lớp {sec.section_code} ({subj_name}) vào {sec.schedule}"
                    return True, msg

        return False, None

    @staticmethod
    def check_prerequisites_met(student_id: int, subject: SubjectModel):
        """
        Kiểm tra xem sinh viên đã đạt tất cả các môn tiên quyết của `subject` chưa.
        Trả về: (all_passed: bool, missing_prereqs: list[str])
        """
        if not subject or not subject.prerequisites:
            return True, []

        missing = []
        for prereq in subject.prerequisites:
            grades = GradeModel.query.filter_by(
                student_id=student_id,
                subject_id=prereq.id
            ).all()
            passed = any(g.is_passed for g in grades)
            if not passed:
                missing.append(prereq.subject_name)

        if missing:
            return False, missing
        return True, []

    @staticmethod
    def enroll_student(student_id: int, section_id: int):
        """Đăng ký lớp học phần cho sinh viên với đầy đủ kiểm tra điều kiện."""
        section = CourseSectionModel.query.get(section_id)
        if not section:
            return False, 'Lớp học phần không tồn tại!'

        if section.status != 'open':
            return False, 'Lớp học phần hiện không mở đăng ký!'

        if section.is_full:
            return False, f'Lớp học phần đã đủ sĩ số tối đa ({section.max_students} SV)!'

        # Kiểm tra đã đăng ký lớp này chưa
        existing = EnrollmentModel.query.filter_by(student_id=student_id, section_id=section_id).first()
        if existing and existing.status == 'registered':
            return False, 'Sinh viên đã đăng ký lớp học phần này rồi!'

        # Kiểm tra điều kiện tiên quyết
        prereqs_met, missing = EnrollmentService.check_prerequisites_met(student_id, section.subject)
        if not prereqs_met:
            return False, f"Chưa đạt các môn tiên quyết: {', '.join(missing)}"

        # Kiểm tra trùng lịch
        conflict, conflict_msg = EnrollmentService.check_schedule_conflict(student_id, section)
        if conflict:
            return False, conflict_msg

        if existing:
            existing.status = 'registered'
        else:
            enr = EnrollmentModel(student_id=student_id, section_id=section_id, status='registered')
            db.session.add(enr)

        db.session.commit()
        return True, 'Đăng ký học phần thành công!'

    @staticmethod
    def drop_enrollment(student_id: int, section_id: int):
        """Hủy đăng ký lớp học phần."""
        enrollment = EnrollmentModel.query.filter_by(
            student_id=student_id, section_id=section_id, status='registered'
        ).first()
        if not enrollment:
            return False, 'Không tìm thấy thông tin đăng ký học phần này!'

        db.session.delete(enrollment)
        db.session.commit()
        return True, 'Hủy đăng ký học phần thành công!'
