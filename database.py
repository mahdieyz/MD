import sqlite3
import os
import threading
import shutil
import time

class Database:
    _local = threading.local()

    def __init__(self, db_path=None):
        self.db_path = db_path or os.environ.get("DB_PATH", "bot_database.db")
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._init_db()

    def _get_conn(self):
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_blocked INTEGER DEFAULT 0
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS catalogs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            file_id TEXT NOT NULL,
            file_type TEXT DEFAULT 'document',
            caption TEXT,
            custom_note TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            uploaded_by INTEGER,
            original_filename TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS broadcast_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_text TEXT,
            sent_count INTEGER,
            fail_count INTEGER,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sent_by INTEGER
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS admin_users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.commit()

    def register_user(self, user_id, username=None, first_name=None, last_name=None):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("""INSERT INTO users (user_id, username, first_name, last_name)
                     VALUES (?, ?, ?, ?)
                     ON CONFLICT(user_id) DO UPDATE SET
                     username=excluded.username,
                     first_name=excluded.first_name,
                     last_name=excluded.last_name,
                     last_active=CURRENT_TIMESTAMP""",
                  (user_id, username, first_name, last_name))
        conn.commit()

    def get_all_users(self):
        conn = self._get_conn()
        return conn.execute("SELECT * FROM users ORDER BY last_active DESC").fetchall()

    def get_active_user_ids(self):
        conn = self._get_conn()
        rows = conn.execute("SELECT user_id FROM users WHERE is_blocked = 0").fetchall()
        return [r['user_id'] for r in rows]

    def get_user_count(self):
        conn = self._get_conn()
        return conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()['cnt']

    def get_active_user_count(self):
        conn = self._get_conn()
        return conn.execute("SELECT COUNT(*) as cnt FROM users WHERE is_blocked = 0").fetchone()['cnt']

    def block_user(self, user_id):
        conn = self._get_conn()
        conn.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (user_id,))
        conn.commit()

    def unblock_user(self, user_id):
        conn = self._get_conn()
        conn.execute("UPDATE users SET is_blocked = 0 WHERE user_id = ?", (user_id,))
        conn.commit()

    def add_catalog(self, category, file_id, file_type='document', caption=None, custom_note=None, uploaded_by=None, original_filename=None):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("""INSERT INTO catalogs (category, file_id, file_type, caption, custom_note, uploaded_by, original_filename)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (category, file_id, file_type, caption, custom_note, uploaded_by, original_filename))
        conn.commit()
        return c.lastrowid

    def get_catalogs(self, category=None):
        conn = self._get_conn()
        if category:
            return conn.execute("SELECT * FROM catalogs WHERE category = ? ORDER BY uploaded_at DESC", (category,)).fetchall()
        return conn.execute("SELECT * FROM catalogs ORDER BY uploaded_at DESC").fetchall()

    def get_catalog_by_id(self, catalog_id):
        conn = self._get_conn()
        return conn.execute("SELECT * FROM catalogs WHERE id = ?", (catalog_id,)).fetchone()

    def delete_catalog(self, catalog_id):
        conn = self._get_conn()
        conn.execute("DELETE FROM catalogs WHERE id = ?", (catalog_id,))
        conn.commit()

    def update_catalog_note(self, catalog_id, note):
        conn = self._get_conn()
        conn.execute("UPDATE catalogs SET custom_note = ? WHERE id = ?", (note, catalog_id))
        conn.commit()

    def get_catalog_count(self):
        conn = self._get_conn()
        return conn.execute("SELECT COUNT(*) as cnt FROM catalogs").fetchone()['cnt']

    def get_category_stats(self):
        conn = self._get_conn()
        return conn.execute("SELECT category, COUNT(*) as cnt FROM catalogs GROUP BY category ORDER BY cnt DESC").fetchall()

    def set_setting(self, key, value):
        conn = self._get_conn()
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (key, value))
        conn.commit()

    def get_setting(self, key, default=None):
        conn = self._get_conn()
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row['value'] if row else default

    def get_all_settings(self):
        conn = self._get_conn()
        return conn.execute("SELECT * FROM settings ORDER BY key").fetchall()

    def log_broadcast(self, message_text, sent_count, fail_count, sent_by=None):
        conn = self._get_conn()
        conn.execute("""INSERT INTO broadcast_log (message_text, sent_count, fail_count, sent_by)
                        VALUES (?, ?, ?, ?)""",
                     (message_text, sent_count, fail_count, sent_by))
        conn.commit()

    def get_broadcast_logs(self, limit=50):
        conn = self._get_conn()
        return conn.execute("SELECT * FROM broadcast_log ORDER BY sent_at DESC LIMIT ?", (limit,)).fetchall()

    def backup_to_file(self, backup_path):
        conn = self._get_conn()
        backup_dir = os.path.dirname(backup_path)
        if backup_dir:
            os.makedirs(backup_dir, exist_ok=True)
        backup_conn = sqlite3.connect(backup_path)
        conn.backup(backup_conn)
        backup_conn.close()
        return backup_path

    def restore_from_file(self, restore_path):
        test_conn = sqlite3.connect(restore_path)
        try:
            tables = test_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            table_names = [t[0] for t in tables]
            required = ['users', 'catalogs', 'settings']
            for req in required:
                if req not in table_names:
                    raise ValueError(f"Missing required table: {req}")
        finally:
            test_conn.close()

        pre_backup = self.db_path + '.pre_restore_backup'
        shutil.copy2(self.db_path, pre_backup)

        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

        shutil.copy2(restore_path, self.db_path)
        self._init_db()
        return True

    def get_all_categories(self):
        conn = self._get_conn()
        rows = conn.execute("SELECT DISTINCT category FROM catalogs ORDER BY category").fetchall()
        return [r['category'] for r in rows]
