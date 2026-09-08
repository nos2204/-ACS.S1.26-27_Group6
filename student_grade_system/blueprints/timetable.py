# student_grade_system/blueprints/timetable.py
import re
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, session, flash, abort, request
from persistence.models import (db, UserModel, CourseSectionModel, EnrollmentModel)
from gateway import token_required, admin_required

timetable_bp = Blueprint('timetable', __name__)

WEEKDAY_MAP = {
    2: 'Thứ 2',
    3: 'Thứ 3',
    4: 'Thứ 4',
    5: 'Thứ 5',
    6: 'Thứ 6',
    7: 'Thứ 7',
    8: 'Chủ nhật'
}


def parse_schedule_text(schedule_text):
    if not schedule_text:
        return None

    text = schedule_text.strip().lower()
    weekday = None

    if 'thứ 2' in text or 'thu 2' in text or re.search(r'\bt2\b', text):
        weekday = 2
    elif 'thứ 3' in text or 'thu 3' in text or re.search(r'\bt3\b', text):
        weekday = 3
    elif 'thứ 4' in text or 'thu 4' in text or re.search(r'\bt4\b', text):
        weekday = 4
    elif 'thứ 5' in text or 'thu 5' in text or re.search(r'\bt5\b', text):
        weekday = 5
    elif 'thứ 6' in text or 'thu 6' in text or re.search(r'\bt6\b', text):
        weekday = 6
    elif 'thứ 7' in text or 'thu 7' in text or re.search(r'\bt7\b', text):
        weekday = 7
    elif 'chủ nhật' in text or 'chu nhat' in text or re.search(r'\bcn\b', text):
        weekday = 8

    # Predefined shifts check: T1-3, T4-6, T7-9, T10-12
    if 't1-3' in text or 't1–3' in text or 'tiết 1-3' in text:
        start_time = '06:45'
        end_time = '09:25'
    elif 't4-6' in text or 't4–6' in text or 'tiết 4-6' in text:
        start_time = '09:30'
        end_time = '12:10'
    elif 't7-9' in text or 't7–9' in text or 'tiết 7-9' in text:
        start_time = '13:00'
        end_time = '15:40'
    elif 't10-12' in text or 't10–12' in text or 'tiết 10-12' in text:
        start_time = '15:45'
        end_time = '18:25'
    else:
        time_matches = re.findall(r'(\d{1,2}:\d{2})', schedule_text)
        if len(time_matches) >= 2:
            start_time = time_matches[0]
            end_time = time_matches[1]
        else:
            start_time = '07:00'
            end_time = '09:00'

    return {
        'weekday': weekday,
        'start_time': start_time,
        'end_time': end_time
    }


def time_to_minutes(time_text):
    hour, minute = map(int, time_text.split(':'))
    return hour * 60 + minute


def get_week_start(any_date=None):
    if any_date is None:
        any_date = datetime.today().date()
    return any_date - timedelta(days=any_date.weekday())


def build_week_days(base_date=None):
    week_start = get_week_start(base_date)
    days = []

    for i in range(7):
        current_date = week_start + timedelta(days=i)
        weekday_num = i + 2 if i < 6 else 8
        days.append({
            'index': i,
            'date': current_date,
            'label': WEEKDAY_MAP[weekday_num],
            'weekday_num': weekday_num
        })

    return days


def build_timetable_events(sections):
    events = []
    colors = ['primary', 'orange', 'purple', 'success', 'danger', 'info', 'secondary']

    for index, section in enumerate(sections):
        parsed = parse_schedule_text(section.schedule or '')

        if not parsed or not parsed.get('weekday'):
            continue

        weekday_num = parsed['weekday']
        start_time = parsed['start_time']
        end_time = parsed['end_time']

        start_minutes = time_to_minutes(start_time)
        end_minutes = time_to_minutes(end_time)

        day_index = 6 if weekday_num == 8 else weekday_num - 2

        events.append({
            'id': section.id,
            'section_code': section.section_code,
            'subject_name': section.subject.subject_name if section.subject else f'Môn {section.subject_id}',
            'teacher_name': section.teacher.full_name if section.teacher else 'Chưa phân công',
            'room': section.room or 'Chưa có phòng',
            'schedule_text': section.schedule or 'Chưa nhập lịch',
            'status': section.status or 'open',
            'start_time': start_time,
            'end_time': end_time,
            'start_minutes': start_minutes,
            'end_minutes': end_minutes,
            'duration_minutes': max(45, end_minutes - start_minutes),
            'day_index': day_index,
            'color_class': colors[index % len(colors)]
        })

    return events


def build_event_students(sections):
    event_id_to_students = {}

    for section in sections:
        students = []
        for enrollment in section.enrollments:
            if enrollment.status == 'registered' and enrollment.student:
                students.append(enrollment.student)
        event_id_to_students[section.id] = students

    return event_id_to_students


@timetable_bp.route('/timetable', endpoint='timetable_redirect')
@token_required
def timetable_redirect():
    if session.get('role') == 'student':
        return redirect(url_for('student_timetable'))

    if session.get('role') == 'teacher':
        return redirect(url_for('teacher_timetable'))

    return redirect(url_for('admin_timetable'))


@timetable_bp.route('/student/timetable', endpoint='student_timetable')
@token_required
def student_timetable():
    if session.get('role') not in ['student', 'admin']:
        abort(403)

    # Get date parameter from query string
    date_str = request.args.get('date')
    selected_date = None
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = None

    user = UserModel.query.filter_by(username=session.get('username')).first()

    if session.get('role') == 'admin':
        sections = CourseSectionModel.query.order_by(CourseSectionModel.section_code).all()
        page_title = 'Thời khóa biểu sinh viên'
        page_note = 'Admin đang xem toàn bộ lịch học.'
    else:
        if not user or not user.student_id:
            flash('Tài khoản sinh viên chưa được liên kết với thông tin sinh viên.', 'warning')
            sections = []
        else:
            enrollments = (
                EnrollmentModel.query
                .filter_by(student_id=user.student_id, status='registered')
                .all()
            )
            sections = [e.section for e in enrollments if e.section]

        page_title = 'Lịch học'
        page_note = 'Thời khóa biểu cá nhân của sinh viên.'

    week_days = build_week_days(selected_date)
    events = build_timetable_events(sections)
    event_id_to_students = {}

    return render_template(
        'timetable.html',
        page_title=page_title,
        page_note=page_note,
        timetable_type='student',
        week_days=week_days,
        events=events,
        event_id_to_students=event_id_to_students,
        selected_date=selected_date or datetime.today().date()
    )


@timetable_bp.route('/teacher/timetable', endpoint='teacher_timetable')
@token_required
def teacher_timetable():
    if session.get('role') not in ['teacher', 'admin']:
        abort(403)

    # Get date parameter from query string
    date_str = request.args.get('date')
    selected_date = None
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = None

    user = UserModel.query.filter_by(username=session.get('username')).first()

    if session.get('role') == 'admin':
        sections = CourseSectionModel.query.order_by(CourseSectionModel.section_code).all()
        page_title = 'Thời khóa biểu giảng viên'
        page_note = 'Admin đang xem toàn bộ lịch giảng dạy.'
    else:
        if not user or not user.teacher_id:
            flash('Tài khoản giảng viên chưa được liên kết với thông tin giảng viên.', 'warning')
            sections = []
        else:
            sections = (
                CourseSectionModel.query
                .filter_by(teacher_id=user.teacher_id)
                .order_by(CourseSectionModel.section_code)
                .all()
            )

        page_title = 'Lịch dạy'
        page_note = 'Thời khóa biểu giảng dạy của giảng viên.'

    week_days = build_week_days(selected_date)
    events = build_timetable_events(sections)
    event_id_to_students = build_event_students(sections)

    return render_template(
        'timetable.html',
        page_title=page_title,
        page_note=page_note,
        timetable_type='teacher',
        week_days=week_days,
        events=events,
        event_id_to_students=event_id_to_students,
        selected_date=selected_date or datetime.today().date()
    )


@timetable_bp.route('/admin/timetable', endpoint='admin_timetable')
@token_required
@admin_required
def admin_timetable():
    # Get date parameter from query string
    date_str = request.args.get('date')
    selected_date = None
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = None

    sections = CourseSectionModel.query.order_by(CourseSectionModel.section_code).all()

    week_days = build_week_days(selected_date)
    events = build_timetable_events(sections)
    event_id_to_students = build_event_students(sections)

    return render_template(
        'timetable.html',
        page_title='Thời khóa biểu toàn hệ thống',
        page_note='Admin xem toàn bộ lịch học và lịch dạy.',
        timetable_type='admin',
        week_days=week_days,
        events=events,
        event_id_to_students=event_id_to_students,
        selected_date=selected_date or datetime.today().date()
    )
