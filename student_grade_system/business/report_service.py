# business/report_service.py
import io
import csv
from datetime import datetime
import pandas as pd
from persistence.models import (
    db, StudentModel, SubjectModel, SemesterModel, GradeModel, AuditLog
)
from business.grade_service import GradeService


class ReportService:
    """Nghiệp vụ xuất nhập dữ liệu: CSV Import, Excel Export, PDF Transcript."""

    @staticmethod
    def import_students_from_csv(file_stream, actor: str = 'admin'):
        """Import danh sách sinh viên từ file CSV."""
        added = 0
        skipped = 0
        errors = []

        text = io.TextIOWrapper(file_stream, encoding='utf-8-sig')
        reader = csv.DictReader(text)

        for i, row in enumerate(reader, start=2):
            code = row.get('student_code', '').strip()
            name = row.get('full_name', '').strip()
            if not code or not name:
                errors.append(f"Dòng {i}: thiếu MSSV hoặc họ tên.")
                continue

            if StudentModel.query.filter_by(student_code=code).first():
                skipped += 1
                continue

            dob = None
            dob_str = row.get('date_of_birth', '').strip()
            if dob_str:
                try:
                    dob = datetime.strptime(dob_str, '%Y-%m-%d').date()
                except ValueError:
                    errors.append(f"Dòng {i}: ngày sinh '{dob_str}' không đúng định dạng YYYY-MM-DD.")

            student = StudentModel(
                student_code=code,
                full_name=name,
                gender=row.get('gender', 'Nam').strip() or 'Nam',
                email=row.get('email', '').strip() or None,
                phone=row.get('phone', '').strip() or None,
                class_name=row.get('class_name', '').strip() or None,
                date_of_birth=dob,
            )
            db.session.add(student)
            added += 1

        db.session.commit()

        log = AuditLog(
            actor=actor,
            action='import_students',
            detail=f"Thêm {added}, bỏ qua {skipped}, lỗi {len(errors)}"
        )
        db.session.add(log)
        db.session.commit()

        return added, skipped, errors

    @staticmethod
    def import_grades_from_csv(file_stream, semester_id: int, actor: str = 'admin'):
        """Import bảng điểm từ file CSV theo học kỳ."""
        updated = 0
        errors = []

        text = io.TextIOWrapper(file_stream, encoding='utf-8-sig')
        reader = csv.DictReader(text)

        for i, row in enumerate(reader, start=2):
            sc = row.get('student_code', '').strip()
            subc = row.get('subject_code', '').strip()
            try:
                pg = float(row.get('progress_grade', 0))
                eg = float(row.get('exam_grade', 0))
                assert 0 <= pg <= 10 and 0 <= eg <= 10
            except (ValueError, AssertionError):
                errors.append(f"Dòng {i}: điểm không hợp lệ.")
                continue

            student = StudentModel.query.filter_by(student_code=sc).first()
            subject = SubjectModel.query.filter_by(subject_code=subc).first()
            if not student:
                errors.append(f"Dòng {i}: không tìm thấy MSSV '{sc}'.")
                continue
            if not subject:
                errors.append(f"Dòng {i}: không tìm thấy mã môn '{subc}'.")
                continue

            GradeService.upsert_grade(
                student.id, subject.id, semester_id,
                pg, eg, actor=actor
            )
            updated += 1

        return updated, errors

    @staticmethod
    def export_students_to_excel(file_path: str, semester_id: int = None):
        """Xuất danh sách sinh viên kèm GPA và xếp loại ra file Excel."""
        students = StudentModel.query.order_by(StudentModel.student_code).all()
        rows = []
        for s in students:
            gpa = (GradeService.calculate_student_gpa(s.id, semester_id)
                   if semester_id else s.gpa)
            rows.append({
                'MSSV': s.student_code,
                'Họ và Tên': s.full_name,
                'Giới tính': s.gender,
                'Lớp': s.display_class or '',
                'Email': s.email or '',
                'Điểm TL (GPA/4)': gpa,
                'Xếp loại': GradeService.classify_academic(gpa),
            })
        df = pd.DataFrame(rows)
        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Danh sách SV')
            ws = writer.sheets['Danh sách SV']
            for col in ws.columns:
                max_len = max(len(str(cell.value or '')) for cell in col) + 4
                ws.column_dimensions[col[0].column_letter].width = min(max_len, 40)

    @staticmethod
    def export_transcript_pdf(student_id: int, semester_id: int = None):
        """Xuất bảng điểm cá nhân của sinh viên ra PDF bằng WeasyPrint."""
        try:
            from weasyprint import HTML
        except ImportError:
            raise RuntimeError("Cần cài weasyprint: pip install weasyprint")

        student = StudentModel.query.get_or_404(student_id)
        query = GradeModel.query.filter_by(student_id=student_id)
        if semester_id:
            query = query.filter_by(semester_id=semester_id)
        grades = query.all()
        sem = SemesterModel.query.get(semester_id) if semester_id else None
        sem_name = sem.display_name if sem else 'Toàn khoá'
        gpa = GradeService.calculate_student_gpa(student_id, semester_id)

        rows_html = ''
        for i, g in enumerate(grades, 1):
            rows_html += f"""
            <tr>
                <td style="text-align:center">{i}</td>
                <td>{g.subject.subject_code if g.subject else ''}</td>
                <td>{g.subject.subject_name if g.subject else ''}</td>
                <td style="text-align:center">{g.subject.credits if g.subject else 0}</td>
                <td style="text-align:center">{g.progress_grade}</td>
                <td style="text-align:center">{g.exam_grade}</td>
                <td style="text-align:center;font-weight:bold">{g.final_grade}</td>
                <td style="text-align:center">{g.letter_grade}</td>
                <td style="text-align:center">{g.grade_point_4}</td>
                <td style="text-align:center">{"Đạt" if g.is_passed else "Rớt"}</td>
            </tr>"""

        html_content = f"""
        <!DOCTYPE html>
        <html lang="vi">
        <head>
          <meta charset="UTF-8">
          <style>
            body {{ font-family: Arial, sans-serif; font-size: 13px; margin: 30px; }}
            h2 {{ text-align: center; font-size: 16px; margin-bottom: 4px; }}
            .subtitle {{ text-align: center; color: #555; margin-bottom: 20px; }}
            .info {{ margin-bottom: 16px; }}
            .info span {{ margin-right: 24px; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th {{ background: #212529; color: #fff; padding: 7px; }}
            td {{ border: 1px solid #ccc; padding: 6px; }}
            tr:nth-child(even) td {{ background: #f8f8f8; }}
            .gpa-row {{ margin-top: 16px; font-size: 14px; font-weight: bold; }}
            .footer {{ margin-top: 40px; text-align: right; font-size: 12px; color: #777; }}
          </style>
        </head>
        <body>
          <h2>BẢNG KẾT QUẢ HỌC TẬP</h2>
          <div class="subtitle">Hệ thống Quản lý Sinh viên — QLSV</div>
          <div class="info">
            <span><b>MSSV:</b> {student.student_code}</span>
            <span><b>Họ tên:</b> {student.full_name}</span>
            <span><b>Lớp:</b> {student.display_class or '—'}</span>
            <span><b>Học kỳ:</b> {sem_name}</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>#</th><th>Mã môn</th><th>Tên môn học</th><th>TC</th>
                <th>Điểm QT</th><th>Điểm thi</th><th>Tổng kết</th><th>Chữ</th><th>Điểm (hệ 4)</th><th>KQ</th>
              </tr>
            </thead>
            <tbody>{rows_html}</tbody>
          </table>
          <div class="gpa-row">Điểm tích lũy (GPA) {sem_name}: {gpa}/4.0 — {GradeService.classify_academic(gpa)}</div>
          <div class="footer">Xuất lúc {datetime.now().strftime('%d/%m/%Y %H:%M')}</div>
        </body>
        </html>
        """

        pdf_bytes = HTML(string=html_content).write_pdf()
        return pdf_bytes
