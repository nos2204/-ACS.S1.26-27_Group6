# business/semester_service.py
from datetime import datetime, date
from persistence.models import db, SemesterModel, AuditLog


class SemesterService:
    """Nghiệp vụ quản lý học kỳ, thời hạn, gia hạn học kỳ và trạng thái."""

    @staticmethod
    def get_current_semester():
        """Lấy học kỳ hiện tại hoặc học kỳ mới nhất."""
        sem = SemesterModel.query.filter_by(is_current=True).first()
        if not sem:
            sem = SemesterModel.query.order_by(SemesterModel.academic_year.desc(), SemesterModel.id.desc()).first()
        return sem

    @staticmethod
    def get_all_semesters():
        """Lấy danh sách tất cả học kỳ sắp xếp mới nhất lên đầu."""
        return SemesterModel.query.order_by(SemesterModel.academic_year.desc(), SemesterModel.name).all()

    @staticmethod
    def extend_semester(semester_id: int, new_end_date: date, reason: str, extended_by: str = 'admin'):
        """Gia hạn ngày kết thúc của học kỳ."""
        semester = SemesterModel.query.get(semester_id)
        if not semester:
            return False, 'Học kỳ không tồn tại!'

        if not semester.can_extend:
            return False, f'Học kỳ không thể gia hạn (đã đạt giới hạn tối đa {semester.max_extensions} lần hoặc đã đóng)!'

        if semester.end_date and new_end_date <= semester.end_date:
            return False, 'Ngày kết thúc mới phải sau ngày kết thúc hiện tại!'

        if not semester.original_end_date:
            semester.original_end_date = semester.end_date

        semester.end_date = new_end_date
        semester.extension_count = (semester.extension_count or 0) + 1
        semester.status = 'extended'
        semester.extension_reason = reason.strip() if reason else None
        semester.extended_by = extended_by
        semester.extended_at = datetime.utcnow()

        log = AuditLog(
            actor=extended_by,
            action='extend_semester',
            target=f"Học kỳ {semester.display_name}",
            detail=f"Gia hạn đến {new_end_date.strftime('%d/%m/%Y')}. Lần thứ: {semester.extension_count}. Lý do: {reason}"
        )
        db.session.add(log)
        db.session.commit()
        return True, f'Đã gia hạn học kỳ thành công đến ngày {new_end_date.strftime("%d/%m/%Y")}!'

    @staticmethod
    def set_current_semester(semester_id: int):
        """Đặt một học kỳ làm học kỳ hiện tại."""
        SemesterModel.query.update({SemesterModel.is_current: False})
        sem = SemesterModel.query.get(semester_id)
        if sem:
            sem.is_current = True
            db.session.commit()
            return True, f'Đã đặt "{sem.display_name}" làm học kỳ hiện tại!'
        return False, 'Học kỳ không tồn tại!'
