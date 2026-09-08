import os
import sys
from datetime import datetime, timezone
from flask import Flask, render_template, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from sqlalchemy import inspect as sa_inspect
from flask_migrate import Migrate
from werkzeug.routing import BuildError

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from persistence.models import db, UserModel, SemesterModel
from gateway import generate_csrf_token, validate_csrf
from blueprints.auth import auth_bp
from blueprints.main import main_bp
from blueprints.students import students_bp
from blueprints.grades import grades_bp
from blueprints.sections import sections_bp
from blueprints.timetable import timetable_bp
from blueprints.admin import admin_bp
from blueprints.semesters import semesters_bp

base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(base_dir, '.env'))


def create_app(config=None):
    app = Flask(
        __name__,
        template_folder='presentation/templates',
        static_folder='presentation/static'
    )

    app.secret_key = os.getenv('FLASK_SECRET_KEY', 'quanlidiemsinhvien_secret_key_2026')
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
        'DATABASE_URL',
        'sqlite:///' + os.path.join(base_dir, 'instance', 'student.db')
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

    if config:
        app.config.update(config)

    db.init_app(app)
    Migrate(app, db)

    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(grades_bp)
    app.register_blueprint(sections_bp)
    app.register_blueprint(timetable_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(semesters_bp)

    # Register Endpoint Aliases for backward compatibility with un-prefixed url_for() calls
    for rule in list(app.url_map.iter_rules()):
        if '.' in rule.endpoint:
            short_endpoint = rule.endpoint.split('.', 1)[1]
            if short_endpoint not in app.view_functions:
                app.view_functions[short_endpoint] = app.view_functions[rule.endpoint]
            rules_list = app.url_map._rules_by_endpoint.setdefault(short_endpoint, [])
            if rule not in rules_list:
                rules_list.append(rule)

    # Context Processors
    @app.context_processor
    def inject_globals():
        return {
            'csrf_token': generate_csrf_token,
            'now': lambda: datetime.now(timezone.utc),
        }

    # Before Request CSRF Protection
    @app.before_request
    def csrf_protect():
        exempt = {'auth.login', 'login', 'static'}
        if request.endpoint in exempt:
            return
        validate_csrf()

    # Database Initialization
    _init_database(app)

    # Register Error Handlers
    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html', error=str(e)), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    return app


def _add_column_if_missing(table_name, column_name, column_sql):
    try:
        inspector = sa_inspect(db.engine)
        cols = [c['name'] for c in inspector.get_columns(table_name)]
        if column_name not in cols:
            db.session.execute(db.text(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}"))
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f'[MIGRATION WARNING] {table_name}.{column_name}: {e}')


def _init_database(app):
    with app.app_context():
        try:
            os.makedirs(os.path.join(base_dir, 'instance'), exist_ok=True)
            db.create_all()

            _add_column_if_missing('users', 'student_id', 'student_id INTEGER NULL')
            _add_column_if_missing('users', 'teacher_id', 'teacher_id INTEGER NULL')
            _add_column_if_missing('users', 'failed_login_count', 'failed_login_count INTEGER DEFAULT 0')
            _add_column_if_missing('users', 'locked_until', 'locked_until DATETIME NULL')
            _add_column_if_missing('users', 'created_at', 'created_at DATETIME')
            _add_column_if_missing('students', 'gender', 'gender VARCHAR(10) NULL')
            _add_column_if_missing('students', 'email', 'email VARCHAR(120) NULL')
            _add_column_if_missing('students', 'phone', 'phone VARCHAR(20) NULL')
            _add_column_if_missing('students', 'class_name', 'class_name VARCHAR(50) NULL')
            _add_column_if_missing('students', 'class_id', 'class_id INTEGER NULL')
            _add_column_if_missing('students', 'date_of_birth', 'date_of_birth DATE NULL')
            _add_column_if_missing('students', 'address', 'address VARCHAR(255) NULL')
            _add_column_if_missing('students', 'department_id', 'department_id INTEGER NULL')
            _add_column_if_missing('students', 'gpa', 'gpa FLOAT DEFAULT 0')
            _add_column_if_missing('students', 'academic_rank', 'academic_rank VARCHAR(20) DEFAULT \'Yếu\'')
            _add_column_if_missing('subjects', 'department_id', 'department_id INTEGER NULL')
            _add_column_if_missing('subjects', 'progress_weight', 'progress_weight FLOAT DEFAULT 0.4')
            _add_column_if_missing('subjects', 'exam_weight', 'exam_weight FLOAT DEFAULT 0.6')
            _add_column_if_missing('grades', 'semester_id', 'semester_id INTEGER NULL')
            
            # Migration for semester extension fields
            _add_column_if_missing('semesters', 'start_date', 'start_date DATE NULL')
            _add_column_if_missing('semesters', 'end_date', 'end_date DATE NULL')
            _add_column_if_missing('semesters', 'original_end_date', 'original_end_date DATE NULL')
            _add_column_if_missing('semesters', 'extension_count', 'extension_count INTEGER DEFAULT 0')
            _add_column_if_missing('semesters', 'max_extensions', 'max_extensions INTEGER DEFAULT 3')
            _add_column_if_missing('semesters', 'status', 'status VARCHAR(20) DEFAULT \'active\'')
            _add_column_if_missing('semesters', 'extension_reason', 'extension_reason TEXT NULL')
            _add_column_if_missing('semesters', 'extended_by', 'extended_by VARCHAR(50) NULL')
            _add_column_if_missing('semesters', 'extended_at', 'extended_at DATETIME NULL')

            if not UserModel.query.filter_by(username='admin').first():
                admin = UserModel(username='admin', role='admin')
                admin.set_password('admin123')
                db.session.add(admin)
            if not SemesterModel.query.first():
                sem = SemesterModel(name='Học kỳ 1', academic_year='2024-2025', is_current=True)
                db.session.add(sem)
                db.session.commit()
            current_sem = SemesterModel.query.filter_by(is_current=True).first() or SemesterModel.query.first()
            if current_sem:
                try:
                    db.session.execute(db.text('UPDATE grades SET semester_id = :sid WHERE semester_id IS NULL'), {'sid': current_sem.id})
                except Exception:
                    pass
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f'[LỖI DATABASE]: {e}')


app = create_app()

if __name__ == '__main__':
    os.makedirs(os.path.join(base_dir, 'instance'), exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=False)