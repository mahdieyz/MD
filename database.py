import os
import sqlite3
import threading
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_lock = threading.RLock()


def _resolve_db_path():
    env = os.getenv("DB_PATH")
    if env:
        return env
    if os.path.isdir("/data"):
        return os.path.join("/data", "bot_database.db")
    return "bot_database.db"


DB_PATH = _resolve_db_path()


def get_db_connection():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(DB_PATH, timeout=20.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=20000;")
    # FK is intentionally OFF: catalogs at root use button_id=0 (no parent row).
    return conn


@contextmanager
def get_conn():
    conn = get_db_connection()
    try:
        with _lock:
            yield conn
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
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
            caption TEXT
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')
        _seed_defaults(cursor)


def _seed_defaults(cursor):
    cursor.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('welcome_text', 'به ربات توان سازه خوش آمدید.')"
    )
    cursor.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('contact_text', 'تماس با ما: 021000000')"
    )
    cursor.execute("SELECT COUNT(*) FROM menu_buttons")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO menu_buttons (title, parent_id) VALUES ('محصولات و قیمت‌ها', 0)")


def reset_bot_config():
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM catalogs;")
            cursor.execute("DELETE FROM menu_buttons;")
            cursor.execute("DELETE FROM settings;")
            _seed_defaults(cursor)
        return True
    except Exception as e:
        logger.error("Database Reset Error: %s", e)
        return False


def add_user(user_id, username, full_name):
    with get_conn() as conn:
        conn.execute(
            '''
            INSERT INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                full_name=excluded.full_name
            ''',
            (user_id, username or "", full_name or ""),
        )


def get_all_users():
    with get_conn() as conn:
        users = conn.execute("SELECT * FROM users ORDER BY joined_at DESC").fetchall()
        return [dict(u) for u in users]


def get_user_count():
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def get_buttons(parent_id=0, admin_mode=False):
    with get_conn() as conn:
        if admin_mode:
            buttons = conn.execute(
                "SELECT * FROM menu_buttons WHERE parent_id=? ORDER BY order_index, id",
                (parent_id,),
            ).fetchall()
        else:
            buttons = conn.execute(
                "SELECT * FROM menu_buttons WHERE parent_id=? AND is_hidden=0 ORDER BY order_index, id",
                (parent_id,),
            ).fetchall()
        return [dict(b) for b in buttons]


def get_button(button_id):
    with get_conn() as conn:
        btn = conn.execute("SELECT * FROM menu_buttons WHERE id=?", (button_id,)).fetchone()
        return dict(btn) if btn else None


def add_menu_button(title, parent_id=0):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO menu_buttons (title, parent_id) VALUES (?, ?)",
            (title, parent_id),
        )


def delete_button(button_id):
    with get_conn() as conn:
        cursor = conn.cursor()

        def get_all_child_ids(b_id):
            ids = [b_id]
            children = cursor.execute(
                "SELECT id FROM menu_buttons WHERE parent_id=?", (b_id,)
            ).fetchall()
            for child in children:
                ids.extend(get_all_child_ids(child["id"]))
            return ids

        all_ids = get_all_child_ids(button_id)
        placeholders = ",".join("?" * len(all_ids))
        cursor.execute(f"DELETE FROM catalogs WHERE button_id IN ({placeholders})", all_ids)
        cursor.execute(f"DELETE FROM menu_buttons WHERE id IN ({placeholders})", all_ids)


def add_catalog(button_id, file_id, file_type, caption):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO catalogs (button_id, file_id, file_type, caption) VALUES (?, ?, ?, ?)",
            (button_id, file_id, file_type, caption),
        )


def get_catalogs(button_id):
    with get_conn() as conn:
        catalogs = conn.execute(
            "SELECT * FROM catalogs WHERE button_id=?", (button_id,)
        ).fetchall()
        return [dict(c) for c in catalogs]


def get_catalog(catalog_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM catalogs WHERE id=?", (catalog_id,)).fetchone()
        return dict(row) if row else None


def delete_catalog(catalog_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM catalogs WHERE id=?", (catalog_id,))


def get_setting(key, default=""):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def update_setting(key, value):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
