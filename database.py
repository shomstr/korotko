import sqlite3
import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

DATABASE_URL = os.environ.get("DATABASE_URL", "korotko.db")

def get_db():
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT NOT NULL,
            password_hash TEXT,
            consent_policy INTEGER DEFAULT 0,
            consent_mailing INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    cursor.execute("""
        DELETE FROM users WHERE id NOT IN (
            SELECT MIN(id) FROM users GROUP BY phone
        )
    """)

    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone ON users(phone)")

    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            duration_min INTEGER NOT NULL,
            category TEXT DEFAULT 'main',
            description TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            service_id INTEGER NOT NULL,
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP NOT NULL,
            address TEXT DEFAULT 'amg',
            status TEXT DEFAULT 'active',
            rating INTEGER,
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (service_id) REFERENCES services(id)
        );

        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            must_change_password INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    ''')

    for col in ('address',):
        try:
            cursor.execute(f"ALTER TABLE bookings ADD COLUMN {col} TEXT DEFAULT 'amg'")
        except sqlite3.OperationalError:
            pass

    for col in ('description',):
        try:
            cursor.execute(f"ALTER TABLE services ADD COLUMN {col} TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass

    seed_services(cursor)
    seed_admin(cursor)

    conn.commit()
    conn.close()

def seed_services(cursor):
    cursor.execute("SELECT COUNT(*) FROM services")
    if cursor.fetchone()[0] > 0:
        return

    services = [
        ("Комплекс", 699, 60, "main", "стрижка, равнение бороды, укладка"),
        ("Классик", 500, 45, "main", "стрижка"),
        ("Детская стрижка (до 12 лет)", 399, 30, "main", "стрижка, укладка"),
        ("Детская стрижка (ОВЗ)", 599, 45, "main", "закрытая стрижка, без посторонних людей • стрижка, укладка, доп. услуги"),
        ("Уход за бородой", 199, 20, "extra", "коррекция, оформление"),
        ("Выезд специалиста на дом", 1500, 60, "extra", "мастер приедет к вам"),
        ("Укладка", 150, 20, "extra", "укладка любой сложности"),
    ]
    cursor.executemany(
        "INSERT INTO services (name, price, duration_min, category, description) VALUES (?, ?, ?, ?, ?)",
        services
    )

def seed_admin(cursor):
    cursor.execute("SELECT COUNT(*) FROM admins")
    if cursor.fetchone()[0] > 0:
        return

    pw_hash = generate_password_hash("admin")
    cursor.execute(
        "INSERT INTO admins (username, password_hash, must_change_password) VALUES (?, ?, 1)",
        ("admin", pw_hash)
    )

def get_setting(key):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row['value'] if row else None

def set_setting(key, value):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def check_booking_conflict(cursor, new_start, new_end):
    cursor.execute(
        """SELECT id FROM bookings
           WHERE status = 'active'
           AND (? < datetime(end_time, '+15 minutes'))
           AND (datetime(?, '+15 minutes') > start_time)""",
        (new_start, new_end)
    )
    return cursor.fetchone() is not None
