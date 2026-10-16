import sqlite3
import os
import logging

logger = logging.getLogger(__name__)
DB_PATH = os.getenv("DB_PATH", "bot_database.db")

def get_db_connection():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    # WAL mode reduces "database is locked" issues under concurrent access
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_blocked INTEGER DEFAULT 0
    )''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS menu_buttons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        parent_id INTEGER DEFAULT 0,
        title TEXT NOT NULL,
        is_hidden INTEGER DEFAULT 0,
        order_index INTEGER DEFAULT 0
    )''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS catalogs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        button_id INTEGER,
        file_id TEXT NOT NULL,
        file_type TEXT NOT NULL,
        caption TEXT,
        FOREIGN KEY(button_id) REFERENCES menu_buttons(id) ON DELETE CASCADE
    )''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')

    _seed_defaults(cursor)
    conn.commit()
    conn.close()

def _seed_defaults(cursor):
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('welcome_text', 'به ربات توان سازه خوش آمدید.')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('contact_text', 'تماس با ما: 021000000')")
    # نکته‌ی مهم: دیگر دکمه‌ی پیش‌فرض تکراری ("محصولات و قیمت‌ها") در اینجا ساخته نمی‌شود،
    # چون دقیقاً با دکمه‌ی اصلی کیبورد هم‌نام بود و باعث سردرگمی کاربر می‌شد.
    # دسته‌بندی‌ها باید توسط ادمین از طریق پنل مدیریت اضافه شوند.

def reset_bot_config():
    """بازنشانی کامل دکمه‌ها، کاتالوگ‌ها و تنظیمات متنی"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM catalogs;")
        cursor.execute("DELETE FROM menu_buttons;")
        cursor.execute("DELETE FROM settings;")
        conn.commit()
        _seed_defaults(cursor)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"Database Reset Error: {e}")
        return False
    finally:
        conn.close()

# --- کاربرها ---
def add_user(user_id, username, full_name):
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO users (user_id, username, full_name) 
        VALUES (?, ?, ?) 
        ON CONFLICT(user_id) DO UPDATE SET 
        username=excluded.username, 
        full_name=excluded.full_name
    ''', (user_id, username or "", full_name or ""))
    conn.commit()
    conn.close()

def get_all_users():
    conn = get_db_connection()
    users = conn.execute("SELECT * FROM users ORDER BY joined_at DESC").fetchall()
    conn.close()
    return [dict(u) for u in users]

def get_user_count():
    conn = get_db_connection()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return count

# --- دکمه‌ها و کاتالوگ‌ها ---
def get_buttons(parent_id=0, admin_mode=False):
    conn = get_db_connection()
    if admin_mode:
        buttons = conn.execute("SELECT * FROM menu_buttons WHERE parent_id=? ORDER BY order_index, id", (parent_id,)).fetchall()
    else:
        buttons = conn.execute("SELECT * FROM menu_buttons WHERE parent_id=? AND is_hidden=0 ORDER BY order_index, id", (parent_id,)).fetchall()
    conn.close()
    return [dict(b) for b in buttons]

def get_button(button_id):
    conn = get_db_connection()
    btn = conn.execute("SELECT * FROM menu_buttons WHERE id=?", (button_id,)).fetchone()
    conn.close()
    return dict(btn) if btn else None

def add_menu_button(title, parent_id=0):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO menu_buttons (title, parent_id) VALUES (?, ?)", (title, parent_id))
    conn.commit()
    conn.close()

def delete_button(button_id):
    """حذف بازگشتی دکمه و زیرمنوهای آن"""
    conn = get_db_connection()
    cursor = conn.cursor()

    def get_all_child_ids(b_id):
        ids = [b_id]
        children = cursor.execute("SELECT id FROM menu_buttons WHERE parent_id=?", (b_id,)).fetchall()
        for child in children:
            ids.extend(get_all_child_ids(child['id']))
        return ids

    all_ids = get_all_child_ids(button_id)
    placeholders = ",".join("?" * len(all_ids))
    cursor.execute(f"DELETE FROM catalogs WHERE button_id IN ({placeholders})", all_ids)
    cursor.execute(f"DELETE FROM menu_buttons WHERE id IN ({placeholders})", all_ids)

    conn.commit()
    conn.close()

def add_catalog(button_id, file_id, file_type, caption):
    conn = get_db_connection()
    conn.execute("INSERT INTO catalogs (button_id, file_id, file_type, caption) VALUES (?, ?, ?, ?)", 
                 (button_id, file_id, file_type, caption))
    conn.commit()
    conn.close()

def get_catalogs(button_id):
    conn = get_db_connection()
    catalogs = conn.execute("SELECT * FROM catalogs WHERE button_id=?", (button_id,)).fetchall()
    conn.close()
    return [dict(c) for c in catalogs]

# --- تنظیمات ---
def get_setting(key, default=""):
    conn = get_db_connection()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row['value'] if row else default

def update_setting(key, value):
    conn = get_db_connection()
    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit()
    conn.close()
