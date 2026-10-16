import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "bot_database.db")

def get_db_connection():
    # فعال‌سازی WAL Mode برای جلوگیری از قفل شدن دیتابیس (database is locked)
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn

def init_db():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # جدول کاربران
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_blocked INTEGER DEFAULT 0
    )''')
    
    # جدول دکمه‌های منو
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS menu_buttons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        parent_id INTEGER DEFAULT 0,
        title TEXT NOT NULL,
        is_hidden INTEGER DEFAULT 0,
        order_index INTEGER DEFAULT 0
    )''')
    
    # جدول کاتالوگ‌ها
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS catalogs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        button_id INTEGER,
        file_id TEXT NOT NULL,
        file_type TEXT NOT NULL,
        caption TEXT,
        FOREIGN KEY(button_id) REFERENCES menu_buttons(id) ON DELETE CASCADE
    )''')
    
    # جدول تنظیمات
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
    cursor.execute("SELECT COUNT(*) FROM menu_buttons")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO menu_buttons (title, parent_id) VALUES ('محصولات و قیمت‌ها', 0)")

def reset_bot_config():
    """بازنشانی کامل دکمه‌ها، کاتالوگ‌ها و تنظیمات به حالت اولیه"""
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
        print(f"Database Reset Error: {e}")
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

def toggle_block_user(user_id):
    conn = get_db_connection()
    conn.execute("UPDATE users SET is_blocked = CASE WHEN is_blocked=1 THEN 0 ELSE 1 END WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

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
    conn = get_db_connection()
    conn.execute("DELETE FROM catalogs WHERE button_id=?", (button_id,))
    conn.execute("DELETE FROM menu_buttons WHERE id=?", (button_id,))
    conn.commit()
    conn.close()

def toggle_button_hide(button_id):
    conn = get_db_connection()
    conn.execute("UPDATE menu_buttons SET is_hidden = CASE WHEN is_hidden=1 THEN 0 ELSE 1 END WHERE id=?", (button_id,))
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

def delete_catalog(catalog_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM catalogs WHERE id=?", (catalog_id,))
    conn.commit()
    conn.close()

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
