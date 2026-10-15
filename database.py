import os, json, sqlite3
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "bot_database.db")

class Database:
    def __init__(self):
        self.db_name = DB_PATH
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
                note TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, value TEXT
            );
        """)
        c.commit(); c.close()

    def add_user(self, uid, uname, fname, lname):
        c = self.conn(); now = datetime.now().isoformat()
        c.execute("INSERT OR REPLACE INTO users (user_id,username,first_name,last_name,join_date,last_activity) VALUES (?,?,?,?,?,?)",
                  (uid, uname, fname, lname, now, now))
        c.commit(); c.close()

    def get_all_users(self):
        c = self.conn()
        rows = [dict(r) for r in c.execute("SELECT * FROM users").fetchall()]
        c.close(); return rows

    def add_catalog_file(self, cat_key, title, file_id, file_name="", note=""):
        c = self.conn()
        c.execute("INSERT INTO catalogs (category_key, title, file_id, file_name, note, created_at) VALUES (?,?,?,?,?,?)",
                  (cat_key, title, file_id, file_name, note, datetime.now().isoformat()))
        c.commit(); c.close()

    def get_catalogs(self, cat_key):
        c = self.conn()
        rows = [dict(r) for r in c.execute("SELECT * FROM catalogs WHERE category_key=? ORDER BY id ASC", (cat_key,)).fetchall()]
        c.close(); return rows

    def delete_catalog(self, cat_id):
        c = self.conn()
        c.execute("DELETE FROM catalogs WHERE id=?", (cat_id,))
        c.commit(); c.close()

    def set_setting(self, key, val):
        c = self.conn()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, val))
        c.commit(); c.close()

    def get_setting(self, key, default=""):
        c = self.conn()
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        c.close(); return r["value"] if r else default

    def get_stats(self):
        c = self.conn()
        u = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        cat = c.execute("SELECT COUNT(*) FROM catalogs").fetchone()[0]
        c.close()
        return {"total_users": u, "total_files": cat}
