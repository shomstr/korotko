import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from database import init_db, get_db, check_booking_conflict, get_setting, set_setting
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.permanent_session_lifetime = timedelta(hours=2)

init_db()

ADDRESSES = {
    "amg": {"name": "АМГ", "address": "ул. Юлиуса Фучика 88А"},
    "korotko": {"name": "КОРОТКО", "address": "ул. Фатыха Амирхана 21б/1"},
}

@app.context_processor
def inject_now():
    return {'now': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}

def normalize_phone(phone):
    import re
    digits = re.sub(r'\D', '', phone)
    if (digits.startswith('7') or digits.startswith('8')) and len(digits) == 11:
        return '7' + digits[1:]
    if len(digits) == 10:
        return '7' + digits
    return digits

WORK_START = 10
WORK_END = 21

def send_email_smtp(recipient, subject, body):
    yandex_user = get_setting("yandex_email")
    yandex_pass = get_setting("yandex_password")
    if not yandex_user or not yandex_pass:
        return False, "Не настроены данные Яндекс.Почты"

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = yandex_user
    msg['To'] = recipient

    text_part = MIMEText(body, 'plain', 'utf-8')
    html_part = MIMEText(
        f"<html><body style='font-family:sans-serif;padding:20px'>{body.replace(chr(10), '<br>')}</body></html>",
        'html', 'utf-8'
    )
    msg.attach(text_part)
    msg.attach(html_part)

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.yandex.ru", 465, context=ctx) as server:
            server.login(yandex_user, yandex_pass)
            server.sendmail(yandex_user, [recipient], msg.as_string())
        return True, "Отправлено"
    except smtplib.SMTPAuthenticationError:
        return False, "Ошибка авторизации. Проверьте логин/пароль или пароль приложения."
    except smtplib.SMTPException as e:
        return False, f"Ошибка SMTP: {e}"
    except Exception as e:
        return False, f"Ошибка: {e}"

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_id'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

def get_available_slots(date_str, service_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT duration_min FROM services WHERE id = ?", (service_id,))
    svc = cursor.fetchone()
    if not svc:
        conn.close()
        return []
    duration = svc['duration_min']
    cursor.execute(
        """SELECT start_time, end_time FROM bookings
           WHERE status = 'active' AND date(start_time) = ?""",
        (date_str,)
    )
    existing = cursor.fetchall()
    conn.close()

    existing_parsed = []
    for ex in existing:
        st = datetime.strptime(ex['start_time'], "%Y-%m-%d %H:%M:%S")
        et = datetime.strptime(ex['end_time'], "%Y-%m-%d %H:%M:%S")
        existing_parsed.append((st, et))

    slots = []
    cur = datetime.strptime(f"{date_str} {WORK_START}:00", "%Y-%m-%d %H:%M")
    end_bound = datetime.strptime(f"{date_str} {WORK_END}:00", "%Y-%m-%d %H:%M")
    while cur + timedelta(minutes=duration) <= end_bound:
        slot_end = cur + timedelta(minutes=duration)
        conflict = False
        for es, ee in existing_parsed:
            if cur < ee + timedelta(minutes=15) and slot_end + timedelta(minutes=15) > es:
                conflict = True
                break
        if not conflict:
            slots.append({
                "start": cur.strftime("%H:%M"),
                "end": slot_end.strftime("%H:%M")
            })
        cur += timedelta(minutes=15)
    return slots

@app.route("/")
def index():
    return render_template("index.html", addresses=ADDRESSES)

@app.route("/api/services")
def api_services():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM services ORDER BY id")
    services = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify(services)

@app.route("/api/slots")
def api_slots():
    service_id = request.args.get("service_id", type=int)
    date_str = request.args.get("date")
    if not service_id or not date_str:
        return jsonify({"error": "service_id and date required"}), 400
    slots = get_available_slots(date_str, service_id)
    return jsonify(slots)

@app.route("/api/book", methods=["POST"])
def api_book():
    data = request.get_json()
    name = (data.get("name") or "").strip()
    phone = normalize_phone(data.get("phone") or "")
    email = (data.get("email") or "").strip()
    try:
        service_id = int(data.get("service_id", 0))
    except (TypeError, ValueError):
        service_id = 0
    date_str = data.get("date")
    time_str = data.get("time")
    address = data.get("address", "amg")
    consent_policy = int(data.get("consent_policy", 0))
    consent_mailing = int(data.get("consent_mailing", 0))

    if address not in ADDRESSES:
        address = "amg"

    if not all([name, phone, email, service_id, date_str, time_str]):
        return jsonify({"error": "Заполните все поля"}), 400
    if not consent_policy:
        return jsonify({"error": "Необходимо согласие с политикой конфиденциальности"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT duration_min FROM services WHERE id = ?", (service_id,))
    svc = cursor.fetchone()
    if not svc:
        conn.close()
        return jsonify({"error": "Услуга не найдена"}), 404

    duration = svc["duration_min"]
    try:
        start_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        conn.close()
        return jsonify({"error": "Неверный формат времени"}), 400
    end_dt = start_dt + timedelta(minutes=duration)
    start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")

    if check_booking_conflict(cursor, start_str, end_str):
        conn.close()
        return jsonify({"error": "Это время уже занято"}), 409

    cursor.execute(
        "SELECT id FROM users WHERE phone = ?", (phone,)
    )
    user = cursor.fetchone()
    if user:
        user_id = user["id"]
        cursor.execute(
            "UPDATE users SET name = ?, email = ?, consent_mailing = ? WHERE id = ?",
            (name, email, consent_mailing, user_id)
        )
    else:
        cursor.execute(
            """INSERT INTO users (name, phone, email, consent_policy, consent_mailing)
               VALUES (?, ?, ?, ?, ?)""",
            (name, phone, email, consent_policy, consent_mailing)
        )
        user_id = cursor.lastrowid

    cursor.execute(
        "INSERT INTO bookings (user_id, service_id, start_time, end_time, address, status) VALUES (?, ?, ?, ?, ?, 'active')",
        (user_id, service_id, start_str, end_str, address)
    )
    conn.commit()
    conn.close()

    session["user_phone"] = phone
    session.permanent = True

    return jsonify({"success": True, "message": "Запись создана! Мы свяжемся с вами для подтверждения."})

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if request.method == "POST":
        phone = normalize_phone(request.form.get("phone", ""))
        if phone:
            session["user_phone"] = phone
            session.permanent = True
        return redirect(url_for("profile"))

    phone = session.get("user_phone")
    bookings = []
    user = None
    if phone:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE phone = ?", (phone,))
        user = cursor.fetchone()
        cursor.execute(
            """SELECT b.id, b.start_time, b.end_time, b.status, b.rating, b.address,
                      s.name as service_name
               FROM bookings b JOIN services s ON b.service_id = s.id
               WHERE b.user_id = (SELECT id FROM users WHERE phone = ?)
               ORDER BY b.start_time DESC""",
            (phone,)
        )
        bookings = [dict(r) for r in cursor.fetchall()]
        conn.close()
    return render_template("profile.html", bookings=bookings, user=user, addresses=ADDRESSES)

@app.route("/api/rate", methods=["POST"])
def api_rate():
    data = request.get_json()
    try:
        booking_id = int(data.get("booking_id", 0))
        rating = int(data.get("rating", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Неверные данные"}), 400
    if not booking_id or rating not in range(1, 6):
        return jsonify({"error": "Неверные данные"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE bookings SET rating = ? WHERE id = ? AND status = 'active' AND datetime(end_time) < datetime('now')",
        (rating, booking_id)
    )
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    if not affected:
        return jsonify({"error": "Нельзя оценить будущую запись"}), 400
    return jsonify({"success": True, "message": "Спасибо за оценку!"})

@app.route("/logout")
def logout():
    session.pop("user_phone", None)
    return redirect(url_for("index"))

@app.route("/admin", methods=["GET", "POST"])
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM admins WHERE username = ?", (username,))
        admin = cursor.fetchone()
        conn.close()
        if admin and check_password_hash(admin["password_hash"], password):
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]
            session["must_change_password"] = admin["must_change_password"]
            if admin["must_change_password"]:
                return redirect(url_for("admin_change_password"))
            return redirect(url_for("admin_dashboard"))
        flash("Неверный логин или пароль", "error")
    return render_template("admin/login.html")

@app.route("/admin/change-password", methods=["GET", "POST"])
@admin_required
def admin_change_password():
    if request.method == "POST":
        new_pass = request.form.get("new_password", "").strip()
        confirm = request.form.get("confirm_password", "").strip()
        if len(new_pass) < 4:
            flash("Пароль должен быть минимум 4 символа", "error")
        elif new_pass != confirm:
            flash("Пароли не совпадают", "error")
        else:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE admins SET password_hash = ?, must_change_password = 0 WHERE id = ?",
                (generate_password_hash(new_pass), session["admin_id"])
            )
            conn.commit()
            conn.close()
            session["must_change_password"] = 0
            flash("Пароль успешно изменен", "success")
            return redirect(url_for("admin_dashboard"))
    return render_template("admin/change_password.html")

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM users")
    users_count = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(*) as cnt FROM bookings")
    bookings_count = cursor.fetchone()["cnt"]
    cursor.execute(
        """SELECT b.id, u.name, u.phone, s.name as service, b.start_time, b.status, b.address
           FROM bookings b
           JOIN users u ON b.user_id = u.id
           JOIN services s ON b.service_id = s.id
           ORDER BY b.created_at DESC LIMIT 10"""
    )
    recent = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return render_template("admin/dashboard.html",
                           users_count=users_count,
                           bookings_count=bookings_count,
                           recent=recent,
                           addresses=ADDRESSES)

@app.route("/admin/users")
@admin_required
def admin_users():
    conn = get_db()
    cursor = conn.cursor()
    search = request.args.get("search", "").strip()
    if search:
        cursor.execute(
            """SELECT u.*, (SELECT COUNT(*) FROM bookings WHERE user_id = u.id) as booking_count
               FROM users u
               WHERE u.name LIKE ? OR u.phone LIKE ? OR u.email LIKE ?
               ORDER BY u.id DESC""",
            (f"%{search}%", f"%{search}%", f"%{search}%")
        )
    else:
        cursor.execute(
            """SELECT u.*, (SELECT COUNT(*) FROM bookings WHERE user_id = u.id) as booking_count
               FROM users u ORDER BY u.id DESC"""
        )
    users = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return render_template("admin/users.html", users=users, search=search)

@app.route("/admin/user/<int:user_id>")
@admin_required
def admin_user_detail(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        flash("Пользователь не найден", "error")
        return redirect(url_for("admin_users"))
    cursor.execute(
        """SELECT b.*, s.name as service_name FROM bookings b
           JOIN services s ON b.service_id = s.id
           WHERE b.user_id = ? ORDER BY b.start_time DESC""",
        (user_id,)
    )
    bookings = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return render_template("admin/user_detail.html", user=dict(user), bookings=bookings, addresses=ADDRESSES)

@app.route("/admin/user/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE bookings SET user_id = NULL WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    flash("Пользователь удален", "success")
    return redirect(url_for("admin_users"))

@app.route("/admin/mailing", methods=["GET", "POST"])
@admin_required
def admin_mailing():
    if request.method == "POST":
        action = request.form.get("action", "")

        if action == "save_settings":
            yandex_email = request.form.get("yandex_email", "").strip()
            yandex_password = request.form.get("yandex_password", "").strip()
            if yandex_email:
                set_setting("yandex_email", yandex_email)
            if yandex_password:
                set_setting("yandex_password", yandex_password)
            flash("Настройки SMTP сохранены", "success")
            return redirect(url_for("admin_mailing"))

        if action == "test":
            test_email = request.form.get("test_email", "").strip()
            if test_email:
                ok, msg = send_email_smtp(test_email, "Тестовое письмо", "Если вы видите это письмо — SMTP настроен правильно!")
                flash(f"Тест: {msg}", "success" if ok else "error")
            else:
                flash("Укажите email для теста", "error")
            return redirect(url_for("admin_mailing"))

        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "").strip()
        if not subject or not body:
            flash("Заполните тему и текст письма", "error")
            return redirect(url_for("admin_mailing"))

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT email FROM users WHERE consent_mailing = 1 AND email != ''"
        )
        recipients = [r["email"] for r in cursor.fetchall()]
        conn.close()

        if not recipients:
            flash("Нет подписчиков на рассылку", "error")
            return redirect(url_for("admin_mailing"))

        sent = 0
        errors = 0
        for email in recipients:
            ok, _ = send_email_smtp(email, subject, body)
            if ok:
                sent += 1
            else:
                errors += 1

        flash(f"Рассылка: {sent} отправлено, {errors} с ошибками", "success" if sent else "error")
        return redirect(url_for("admin_mailing"))

    yandex_email = get_setting("yandex_email") or ""
    yandex_password = get_setting("yandex_password") or ""
    return render_template("admin/mailing.html",
                           yandex_email=yandex_email,
                           yandex_password="*" * len(yandex_password) if yandex_password else "")

@app.route("/admin/mailing/preview", methods=["POST"])
@admin_required
def admin_mailing_preview():
    subject = request.form.get("subject", "").strip()
    body = request.form.get("body", "").strip()
    return jsonify({"subject": subject, "body": body})

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_id", None)
    session.pop("admin_username", None)
    return redirect(url_for("admin_login"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
