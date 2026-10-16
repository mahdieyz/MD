import os, json, sqlite3, shutil, logging
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "bot_database.db")

class Database:
    def __init__(self):
        self.db_name = DB_PATH
        # FIX #1: Ensure parent directory exists (needed for Railway Volume)
        db_dir = os.path.dirname(self.db_name)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logging.info(f"📁 Created DB directory: {db_dir}")
        self.init_db()

    def conn(self):
        c = sqlite3.connect(self.db_name)
        c.row_factory = sqlite3.Row
        return c

    def init_db(self):
        c = self.conn()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, username TEXT,
                first_name TEXT, last_name TEXT,
                join_date TEXT, last_activity TEXT
            );
            CREATE TABLE IF NOT EXISTS catalogs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_key TEXT,
                title TEXT,
                file_id TEXT,
                file_name TEXT,
                file_type TEXT DEFAULT 'document',
                note TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, value TEXT
            );
        """)
        c.commit(); c.close()

    # ── USERS ──
    def add_user(self, uid, uname, fname, lname):
        conn = self.conn()
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO users (user_id,username,first_name,last_name,join_date,last_activity) "
            "VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "username=excluded.username, first_name=excluded.first_name, "
            "last_name=excluded.last_name, last_activity=excluded.last_activity",
            (uid, uname, fname, lname, now, now))
        conn.commit(); conn.close()

    def get_all_users(self):
        c = self.conn()
        rows = [dict(r) for r in c.execute("SELECT * FROM users").fetchall()]
        c.close(); return rows

    # ── CATALOGS ──
    def add_catalog_file(self, cat_key, title, file_id, file_name="", note="", file_type="document"):
        c = self.conn()
        c.execute(
            "INSERT INTO catalogs (category_key, title, file_id, file_name, file_type, note, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (cat_key, title, file_id, file_name, file_type, note, datetime.now().isoformat()))
        c.commit(); c.close()

    def get_catalogs(self, cat_key):
        c = self.conn()
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM catalogs WHERE category_key=? ORDER BY id ASC", (cat_key,)).fetchall()]
        c.close(); return rows

    def get_catalog_by_id(self, cat_id):
        c = self.conn()
        r = c.execute("SELECT * FROM catalogs WHERE id=?", (cat_id,)).fetchone()
        c.close(); return dict(r) if r else None

    def delete_catalog(self, cat_id):
        c = self.conn()
        c.execute("DELETE FROM catalogs WHERE id=?", (cat_id,))
        c.commit(); c.close()

    def count_catalogs_by_category(self):
        c = self.conn()
        rows = c.execute(
            "SELECT category_key, COUNT(*) as cnt FROM catalogs GROUP BY category_key"
        ).fetchall()
        c.close(); return {r["category_key"]: r["cnt"] for r in rows}

    # ── SETTINGS ──
    def set_setting(self, key, val):
        c = self.conn()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, val))
        c.commit(); c.close()

    def get_setting(self, key, default=""):
        c = self.conn()
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        c.close(); return r["value"] if r else default

    # ── STATS ──
    def get_stats(self):
        c = self.conn()
        u = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        f = c.execute("SELECT COUNT(*) FROM catalogs").fetchone()[0]
        c.close()
        return {"total_users": u, "total_files": f}

    # ── BACKUP / RESTORE ──
    def backup_to_file(self, target_path):
        """Safe backup using SQLite's online backup API."""
        src = sqlite3.connect(self.db_name)
        dst = sqlite3.connect(target_path)
        with dst:
            src.backup(dst)
        dst.close()
        src.close()
        return target_path

    def restore_from_file(self, source_path):
        """Validate and restore from a .db file. Returns True on success."""
        try:
            # FIX #6: Validate it's a real SQLite DB
            test = sqlite3.connect(source_path)
            test.execute("SELECT name FROM sqlite_master WHERE type='table'")
            test.close()
            # Backup current, then replace
            if os.path.exists(self.db_name):
                self.backup_to_file(self.db_name + ".pre_restore_backup")
            shutil.copy2(source_path, self.db_name)
            return True
        except Exception as e:
            logging.error(f"Restore failed: {e}")
            return False
