from datetime import datetime
from functools import wraps
import os
import secrets
import tempfile

import pandas as pd
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
database_url = os.environ.get("DATABASE_URL", "sqlite:///database.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

is_production = os.environ.get("APP_ENV", "").lower() == "production"

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "supersecretkey")
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = is_production
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    employment_type = db.Column(db.String(20), nullable=False)
    active = db.Column(db.Boolean, default=True)


class TimeEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime)
    break_minutes = db.Column(db.Integer, default=0)
    entry_type = db.Column(db.String(20), default="work")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    action = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


def calculate_break(start, end):
    duration = end - start
    hours = duration.total_seconds() / 3600
    if hours > 9:
        return 45
    if hours > 6:
        return 30
    return 0


def log_action(user_id, action):
    db.session.add(AuditLog(user_id=user_id, action=action))


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)


def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for("employee_login"))
            if role and user.role != role:
                flash("Keine Berechtigung.", "error")
                if user.role == "admin":
                    return redirect(url_for("admin"))
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def parse_datetime(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M")


@app.context_processor
def inject_user():
    return {"current_user": current_user()}


@app.route("/")
def home():
    return redirect(url_for("employee_login"))


@app.route("/login/employee", methods=["GET", "POST"])
def employee_login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        user = User.query.filter_by(email=email, active=True).first()

        if not user or not check_password_hash(user.password, password):
            flash("Login fehlgeschlagen.", "error")
            return render_template("login.html", login_type="employee")

        if user.role != "employee":
            flash("Bitte den Admin-Login nutzen.", "error")
            return render_template("login.html", login_type="employee")

        session["user_id"] = user.id
        session["role"] = user.role
        log_action(user.id, "Mitarbeiter Login")
        db.session.commit()
        return redirect(url_for("dashboard"))

    return render_template("login.html", login_type="employee")


@app.route("/login/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        user = User.query.filter_by(email=email, active=True).first()

        if not user or not check_password_hash(user.password, password):
            flash("Login fehlgeschlagen.", "error")
            return render_template("login.html", login_type="admin")

        if user.role != "admin":
            flash("Bitte den Mitarbeiter-Login nutzen.", "error")
            return render_template("login.html", login_type="admin")

        session["user_id"] = user.id
        session["role"] = user.role
        log_action(user.id, "Admin Login")
        db.session.commit()
        return redirect(url_for("admin"))

    return render_template("login.html", login_type="admin")


@app.route("/dashboard")
@login_required(role="employee")
def dashboard():
    user = current_user()
    entries = (
        TimeEntry.query.filter_by(user_id=user.id)
        .order_by(TimeEntry.start_time.desc())
        .limit(50)
        .all()
    )
    active_entry = TimeEntry.query.filter_by(user_id=user.id, end_time=None).first()
    return render_template(
        "dashboard.html", entries=entries, active_entry=active_entry
    )


@app.route("/start")
@login_required(role="employee")
def start_work():
    user = current_user()
    open_entry = TimeEntry.query.filter_by(user_id=user.id, end_time=None).first()
    if open_entry:
        flash("Es laeuft bereits eine Zeiterfassung.", "error")
        return redirect(url_for("dashboard"))

    entry = TimeEntry(user_id=user.id, start_time=datetime.now(), entry_type="work")
    db.session.add(entry)
    log_action(user.id, "Arbeitszeit gestartet")
    db.session.commit()
    flash("Arbeitszeit gestartet.", "success")
    return redirect(url_for("dashboard"))


@app.route("/stop")
@login_required(role="employee")
def stop_work():
    user = current_user()
    entry = TimeEntry.query.filter_by(user_id=user.id, end_time=None).first()
    if not entry:
        flash("Keine laufende Zeiterfassung gefunden.", "error")
        return redirect(url_for("dashboard"))

    entry.end_time = datetime.now()
    entry.break_minutes = calculate_break(entry.start_time, entry.end_time)
    log_action(user.id, "Arbeitszeit gestoppt")
    db.session.commit()
    flash("Arbeitszeit gestoppt.", "success")
    return redirect(url_for("dashboard"))


@app.route("/manual_entry", methods=["POST"])
@login_required(role="employee")
def manual_entry():
    user = current_user()
    entry_type = request.form.get("entry_type", "work")

    try:
        start_time = parse_datetime(request.form["start_time"])
        end_time = parse_datetime(request.form["end_time"])
    except ValueError:
        flash("Datum/Uhrzeit ist ungueltig.", "error")
        return redirect(url_for("dashboard"))

    if end_time <= start_time:
        flash("Ende muss spaeter als Start sein.", "error")
        return redirect(url_for("dashboard"))

    break_minutes = 0 if entry_type in {"vacation", "sick"} else calculate_break(start_time, end_time)

    db.session.add(
        TimeEntry(
            user_id=user.id,
            start_time=start_time,
            end_time=end_time,
            break_minutes=break_minutes,
            entry_type=entry_type,
        )
    )
    log_action(user.id, f"Manueller Eintrag ({entry_type})")
    db.session.commit()
    flash("Eintrag gespeichert.", "success")
    return redirect(url_for("dashboard"))


@app.route("/admin")
@login_required(role="admin")
def admin():
    users = User.query.order_by(User.active.desc(), User.name.asc()).all()
    entries = TimeEntry.query.order_by(TimeEntry.created_at.desc()).limit(100).all()
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(80).all()
    return render_template("admin.html", users=users, entries=entries, logs=logs)


@app.route("/create_user", methods=["POST"])
@login_required(role="admin")
def create_user():
    admin_user = current_user()

    name = request.form["name"].strip()
    email = request.form["email"].strip().lower()
    role = request.form["role"]
    employment_type = request.form["employment_type"]
    password = request.form.get("password", "").strip()

    if not name or not email:
        flash("Name und Email sind erforderlich.", "error")
        return redirect(url_for("admin"))

    if User.query.filter_by(email=email).first():
        flash("Email existiert bereits.", "error")
        return redirect(url_for("admin"))

    if not password:
        password = secrets.token_urlsafe(8)

    new_user = User(
        name=name,
        email=email,
        password=generate_password_hash(password),
        role=role,
        employment_type=employment_type,
    )

    db.session.add(new_user)
    log_action(admin_user.id, f"User erstellt: {email} ({role})")
    db.session.commit()

    flash(
        f"Nutzer erstellt. Erstpasswort fuer {email}: {password}",
        "success",
    )
    return redirect(url_for("admin"))


@app.route("/toggle_user/<int:user_id>")
@login_required(role="admin")
def toggle_user(user_id):
    admin_user = current_user()
    user = db.session.get(User, user_id)
    if not user:
        flash("Nutzer nicht gefunden.", "error")
        return redirect(url_for("admin"))

    if user.id == admin_user.id:
        flash("Eigenes Admin-Konto kann nicht deaktiviert werden.", "error")
        return redirect(url_for("admin"))

    user.active = not user.active
    state = "aktiviert" if user.active else "deaktiviert"
    log_action(admin_user.id, f"User {user.email} {state}")
    db.session.commit()
    flash(f"Nutzer {state}.", "success")
    return redirect(url_for("admin"))


@app.route("/export")
@login_required(role="admin")
def export():
    admin_user = current_user()
    entries = TimeEntry.query.order_by(TimeEntry.start_time.desc()).all()

    data = []
    for entry in entries:
        user = db.session.get(User, entry.user_id)
        data.append(
            {
                "Mitarbeiter": user.name if user else entry.user_id,
                "Email": user.email if user else "-",
                "Typ": entry.entry_type,
                "Start": entry.start_time,
                "Ende": entry.end_time,
                "Pause (Min)": entry.break_minutes,
            }
        )

    df = pd.DataFrame(data)
    file_path = os.path.join(tempfile.gettempdir(), "export.xlsx")
    df.to_excel(file_path, index=False)

    log_action(admin_user.id, "Excel Export")
    db.session.commit()
    return send_file(file_path, as_attachment=True)


@app.route("/logout")
def logout():
    user = current_user()
    if user:
        log_action(user.id, "Logout")
        db.session.commit()
    session.clear()
    return redirect(url_for("employee_login"))


def ensure_default_admin():
    db.create_all()
    default_admin = User.query.filter_by(email="admin@admin.de").first()
    if not default_admin:
        db.session.add(
            User(
                name="Admin",
                email="admin@admin.de",
                password=generate_password_hash("admin123"),
                role="admin",
                employment_type="fest",
            )
        )
        db.session.commit()


with app.app_context():
    ensure_default_admin()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
    )
