import os
import sqlite3
import shutil

DB_PATH = os.getenv("DB_PATH", "data/bot.db")


class Database:
    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        self.init_db()

    def conn(self):
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        return conn

    def _table_exists(self, table_name):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        res = cur.fetchone()
        conn.close()
        return res is not None

    def _column_exists(self, table_name, column_name):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table_name})")
        res = [row[1] for row in cur.fetchall()]
        conn.close()
        return column_name in res

    def init_db(self):
        conn = self.conn()
        cur = conn.cursor()

        if not self._table_exists("users"):
            cur.execute("""
                CREATE TABLE users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    joined_at TEXT
                )
            """)
        else:
            if not self._column_exists("users", "joined_at"):
                cur.execute("ALTER TABLE users ADD COLUMN joined_at TEXT")

        if not self._table_exists("settings"):
            cur.execute("""
                CREATE TABLE settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

        if not self._table_exists("menu_buttons"):
            cur.execute("""
                CREATE TABLE menu_buttons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent_id INTEGER DEFAULT 0,
                    title TEXT,
                    sort_order INTEGER DEFAULT 0
                )
            """)

        if not self._table_exists("catalogs"):
            cur.execute("""
                CREATE TABLE catalogs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    button_id INTEGER,
                    file_id TEXT,
                    file_name TEXT,
                    note TEXT,
                    file_type TEXT,
                    category_key TEXT,
                    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

        if not self._table_exists("activity_log"):
            cur.execute("""
                CREATE TABLE activity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    admin_name TEXT,
                    action TEXT,
                    details TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)

        conn.commit()
        conn.close()

        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM menu_buttons")
        count = cur.fetchone()[0]
        conn.close()

        if count == 0:
            self._seed_defaults()

    def _seed_defaults(self):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM catalogs")
        cur.execute("DELETE FROM menu_buttons")

        roots = [
            "مگنتار و چراغ لاینی",
            "کلید ، پریز هوشمند و مکانیکی",
            "صنعتی ساختمانی",
            "نمای ساختمان - محوطه - استخری",
            "سیم و کابل",
            "آیفون",
            "اعلان حریق",
            "پریز کابینتی میلو",
            "پریز کابینتی ملونی",
        ]
        root_ids = {}
        for title in roots:
            cur.execute(
                "INSERT INTO menu_buttons (parent_id, title, sort_order) VALUES (0, ?, 0)",
                (title,),
            )
            root_ids[title] = cur.lastrowid

        pid = root_ids["کلید ، پریز هوشمند و مکانیکی"]
        for child in ["پریز و کلید هوشمند", "کلید مکانیکی"]:
            cur.execute(
                "INSERT INTO menu_buttons (parent_id, title, sort_order) VALUES (?, ?, 0)",
                (pid, child),
            )

        pid = root_ids["نمای ساختمان - محوطه - استخری"]
        for child in ["مد نور", "شعاع", "انوار"]:
            cur.execute(
                "INSERT INTO menu_buttons (parent_id, title, sort_order) VALUES (?, ?, 0)",
                (pid, child),
            )

        conn.commit()
        conn.close()
        self._migrate_legacy_catalogs()

    def _migrate_legacy_catalogs(self):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT id, button_id, category_key FROM catalogs WHERE button_id = 0 OR button_id IS NULL")
        for row in cur.fetchall():
            catalog_id, old_bid, cat_key = row
            if cat_key:
                cur.execute("SELECT id FROM menu_buttons WHERE title = ?", (cat_key,))
                res = cur.fetchone()
                if res:
                    cur.execute("UPDATE catalogs SET button_id = ? WHERE id = ?", (res[0], catalog_id))
        conn.commit()
        conn.close()

    def reset_menu(self):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM catalogs")
        cur.execute("DELETE FROM menu_buttons")
        conn.commit()
        conn.close()
        self.init_db()

    def add_user(self, user_id, username, first_name):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (user_id, username, first_name, joined_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
        """, (user_id, username, first_name))
        conn.commit()
        conn.close()

    def get_all_users(self):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT user_id, username, first_name FROM users")
        rows = [dict(row) for row in cur.fetchall()]
        conn.close()
        return rows

    def get_user_growth_stats(self):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE date(joined_at) = date('now')")
        today = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE date(joined_at) >= date('now', '-6 days')")
        week = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE date(joined_at) >= date('now', '-29 days')")
        month = cur.fetchone()[0]
        conn.close()
        return {"total": total, "today": today, "week": week, "month": month}

    def get_buttons(self, parent_id=0):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM menu_buttons WHERE parent_id = ? ORDER BY sort_order, id", (parent_id,))
        rows = [dict(row) for row in cur.fetchall()]
        conn.close()
        return rows

    def get_button(self, button_id):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM menu_buttons WHERE id = ?", (button_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_button_by_title_parent(self, title, parent_id=0):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM menu_buttons WHERE title = ? AND parent_id = ? LIMIT 1", (title, parent_id))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def add_button(self, parent_id, title):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("INSERT INTO menu_buttons (parent_id, title, sort_order) VALUES (?, ?, 0)", (parent_id, title))
        btn_id = cur.lastrowid
        conn.commit()
        conn.close()
        return btn_id

    def rename_button(self, button_id, new_title):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("UPDATE menu_buttons SET title = ? WHERE id = ?", (new_title, button_id))
        conn.commit()
        conn.close()

    def delete_button(self, button_id):
        conn = self.conn()
        cur = conn.cursor()

        def delete_recursive(bid):
            cur.execute("DELETE FROM catalogs WHERE button_id = ?", (bid,))
            cur.execute("SELECT id FROM menu_buttons WHERE parent_id = ?", (bid,))
            for (child_id,) in cur.fetchall():
                delete_recursive(child_id)
            cur.execute("DELETE FROM menu_buttons WHERE id = ?", (bid,))

        delete_recursive(button_id)
        conn.commit()
        conn.close()

    def move_button(self, button_id, direction):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT parent_id, sort_order FROM menu_buttons WHERE id = ?", (button_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return
        parent_id, current = row
        if direction == -1:
            cur.execute(
                "SELECT id, sort_order FROM menu_buttons WHERE parent_id = ? AND sort_order < ? ORDER BY sort_order DESC LIMIT 1",
                (parent_id, current),
            )
            prev = cur.fetchone()
            if prev:
                cur.execute("UPDATE menu_buttons SET sort_order = ? WHERE id = ?", (current, prev[0]))
                cur.execute("UPDATE menu_buttons SET sort_order = ? WHERE id = ?", (prev[1], button_id))
        else:
            cur.execute(
                "SELECT id, sort_order FROM menu_buttons WHERE parent_id = ? AND sort_order > ? ORDER BY sort_order ASC LIMIT 1",
                (parent_id, current),
            )
            nxt = cur.fetchone()
            if nxt:
                cur.execute("UPDATE menu_buttons SET sort_order = ? WHERE id = ?", (current, nxt[0]))
                cur.execute("UPDATE menu_buttons SET sort_order = ? WHERE id = ?", (nxt[1], button_id))
        conn.commit()
        conn.close()

    def add_catalog_file(self, button_id, file_id, file_name, note, file_type):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO catalogs (button_id, file_id, file_name, note, file_type, uploaded_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (button_id, file_id, file_name, note, file_type))
        conn.commit()
        conn.close()

    def get_catalogs(self, button_id):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM catalogs WHERE button_id = ? ORDER BY id DESC", (button_id,))
        rows = [dict(row) for row in cur.fetchall()]
        conn.close()
        return rows

    def get_catalog_by_id(self, item_id):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM catalogs WHERE id = ?", (item_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def delete_catalog(self, item_id):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM catalogs WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()

    def get_section_breakdown(self):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT button_id, COUNT(*) FROM catalogs GROUP BY button_id")
        rows = cur.fetchall()
        conn.close()
        return dict(rows)

    def search(self, query):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM menu_buttons WHERE title LIKE ? LIMIT 30",
            (f"%{query}%",),
        )
        buttons = [dict(row) for row in cur.fetchall()]
        cur.execute("""
            SELECT * FROM catalogs WHERE (note LIKE ? OR file_name LIKE ?) LIMIT 30
        """, (f"%{query}%", f"%{query}%"))
        contents = [dict(row) for row in cur.fetchall()]
        conn.close()
        return buttons, contents

    def set_setting(self, key, value):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        conn.close()

    def get_setting(self, key, default=None):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else default

    def log_activity(self, admin_id, admin_name, action, details=""):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO activity_log (admin_id, admin_name, action, details)
            VALUES (?, ?, ?, ?)
        """, (admin_id, admin_name, action, details))
        conn.commit()
        conn.close()

    def get_recent_activity(self, limit=20):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM activity_log ORDER BY id DESC LIMIT ?", (limit,))
        rows = [dict(row) for row in cur.fetchall()]
        conn.close()
        return rows

    def get_stats(self):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        users = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM menu_buttons")
        buttons = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM catalogs")
        catalogs = cur.fetchone()[0]
        conn.close()
        return {"users": users, "buttons": buttons, "catalogs": catalogs}

    def backup_to_file(self, target_path):
        src = sqlite3.connect(DB_PATH)
        dst = sqlite3.connect(target_path)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()

    def restore_from_file(self, source_path):
        with open(source_path, "rb") as f:
            header = f.read(16)
            if header[:6] != b"SQLite format 3\x00":
                raise ValueError("Invalid SQLite file")
        backup_path = DB_PATH + ".pre_restore_backup"
        if os.path.exists(DB_PATH):
            shutil.copy2(DB_PATH, backup_path)
        shutil.copy2(source_path, DB_PATH)
        self.init_db()
