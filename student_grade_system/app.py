# app.py
import os
import sys
from datetime import datetime, timezone
from flask import Flask, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from flask_migrate import Migrate

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

    # Database Initialization & Default Seeding
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


def _init_database(app):
    """Khởi tạo cấu trúc bảng CSDL và tạo dữ liệu ban đầu nếu chưa có."""
    with app.app_context():
        try:
            os.makedirs(os.path.join(base_dir, 'instance'), exist_ok=True)
            db.create_all()

            # Seed default admin account
            if not UserModel.query.filter_by(username='admin').first():
                admin = UserModel(username='admin', role='admin')
                admin.set_password('admin123')
                db.session.add(admin)

            # Seed default semester
            if not SemesterModel.query.first():
                sem = SemesterModel(name='Học kỳ 1', academic_year='2024-2025', is_current=True)
                db.session.add(sem)

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f'[LỖI DATABASE]: {e}')


app = create_app()

if __name__ == '__main__':
    os.makedirs(os.path.join(base_dir, 'instance'), exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=False)