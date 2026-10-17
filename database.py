import os
import sqlite3
import shutil

DB_PATH = os.getenv("DB_PATH", "data/bot.db")

DEFAULT_MENU_TREE = [
    {"title": "مگنتار و چراغ لاینی", "legacy_key": "magnetar_line"},
    {"title": "کلید ، پریز هوشمند و مکانیکی", "children": [
        {"title": "پریز و کلید هوشمند", "legacy_key": "smart_switches"},
        {"title": "کلید مکانیکی", "legacy_key": "mechanical_switches"},
    ]},
    {"title": "صنعتی ساختمانی", "legacy_key": "industrial"},
    {"title": "نمای ساختمان - محوطه - استخری", "children": [
        {"title": "مد نور", "legacy_key": "mod_noor"},
        {"title": "شعاع", "legacy_key": "shaa"},
        {"title": "انوار", "legacy_key": "anvar"},
    ]},
    {"title": "سیم و کابل", "legacy_key": "wire_cable"},
    {"title": "آیفون", "legacy_key": "intercom"},
    {"title": "اعلان حریق", "legacy_key": "fire_alarm"},
    {"title": "پریز کابینتی میلو", "legacy_key": "milo_socket"},
    {"title": "پریز کابینتی ملونی", "legacy_key": "meloni_socket"},
]


class Database:
    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        self.init_db()

    def conn(self):
        connection = sqlite3.connect(DB_PATH)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _table_exists(self, conn, name):
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
        return cur.fetchone() is not None

    def _column_exists(self, conn, table, column):
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        cols = [r["name"] for r in cur.fetchall()]
        return column in cols

    def init_db(self):
        conn = self.conn()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT
            )
        """)
        if not self._column_exists(conn, "users", "joined_at"):
            cur.execute("ALTER TABLE users ADD COLUMN joined_at TEXT")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS menu_buttons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                parent_id INTEGER NOT NULL DEFAULT 0,
                order_index INTEGER NOT NULL DEFAULT 0
            )
        """)

        if self._table_exists(conn, "catalogs"):
            if not self._column_exists(conn, "catalogs", "button_id"):
                cur.execute("ALTER TABLE catalogs ADD COLUMN button_id INTEGER NOT NULL DEFAULT 0")
            if not self._column_exists(conn, "catalogs", "file_type"):
                cur.execute("ALTER TABLE catalogs ADD COLUMN file_type TEXT")
            if not self._column_exists(conn, "catalogs", "category_key"):
                cur.execute("ALTER TABLE catalogs ADD COLUMN category_key TEXT")
            if not self._column_exists(conn, "catalogs", "uploaded_at"):
                cur.execute("ALTER TABLE catalogs ADD COLUMN uploaded_at TEXT")
        else:
            cur.execute("""
                CREATE TABLE catalogs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    button_id INTEGER NOT NULL DEFAULT 0,
                    file_id TEXT,
                    file_name TEXT,
                    note TEXT,
                    file_type TEXT,
                    category_key TEXT,
                    uploaded_at TEXT DEFAULT (datetime('now'))
                )
            """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                admin_name TEXT,
                action TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        conn.commit()

        cur.execute("SELECT COUNT(*) AS c FROM menu_buttons")
        count = cur.fetchone()["c"]
        if count == 0:
            legacy_map = self._seed_defaults(conn)
        else:
            legacy_map = self._build_legacy_map(conn)

        self._migrate_legacy_catalogs(conn, legacy_map)
        conn.close()

    def _insert_tree(self, conn, tree, parent_id, legacy_map):
        cur = conn.cursor()
        for idx, node in enumerate(tree):
            cur.execute(
                "INSERT INTO menu_buttons (title, parent_id, order_index) VALUES (?, ?, ?)",
                (node["title"], parent_id, idx),
            )
            bid = cur.lastrowid
            if "legacy_key" in node:
                legacy_map[node["legacy_key"]] = bid
            if "children" in node:
                self._insert_tree(conn, node["children"], bid, legacy_map)

    def _seed_defaults(self, conn):
        legacy_map = {}
        self._insert_tree(conn, DEFAULT_MENU_TREE, parent_id=0, legacy_map=legacy_map)
        conn.commit()
        return legacy_map

    def _walk_existing_tree(self, conn, tree, parent_id, legacy_map):
        cur = conn.cursor()
        for node in tree:
            cur.execute(
                "SELECT id FROM menu_buttons WHERE title=? AND parent_id=?",
                (node["title"], parent_id),
            )
            row = cur.fetchone()
            if row:
                bid = row["id"]
                if "legacy_key" in node:
                    legacy_map[node["legacy_key"]] = bid
                if "children" in node:
                    self._walk_existing_tree(conn, node["children"], bid, legacy_map)

    def _build_legacy_map(self, conn):
        legacy_map = {}
        self._walk_existing_tree(conn, DEFAULT_MENU_TREE, 0, legacy_map)
        return legacy_map

    def _migrate_legacy_catalogs(self, conn, legacy_map):
        if not legacy_map:
            return
        cur = conn.cursor()
        cur.execute("SELECT id, category_key FROM catalogs WHERE category_key IS NOT NULL AND category_key != ''")
        rows = cur.fetchall()
        for row in rows:
            bid = legacy_map.get(row["category_key"])
            if bid is not None:
                cur.execute(
                    "UPDATE catalogs SET button_id=?, category_key=NULL WHERE id=?",
                    (bid, row["id"]),
                )
        conn.commit()

    def reset_menu(self):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM catalogs")
        cur.execute("DELETE FROM menu_buttons")
        conn.commit()
        conn.close()
        self.init_db()

    # ---- users ----

    def add_user(self, user_id, username, first_name):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (user_id, username, first_name, joined_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
            """,
            (user_id, username, first_name),
        )
        conn.commit()
        conn.close()

    def get_all_users(self):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def get_user_growth_stats(self):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS c FROM users")
        total = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM users WHERE joined_at IS NOT NULL AND date(joined_at) = date('now')")
        today = cur.fetchone()["c"]
        cur.execute(
            "SELECT COUNT(*) AS c FROM users WHERE joined_at IS NOT NULL AND date(joined_at) >= date('now', '-6 days')"
        )
        week = cur.fetchone()["c"]
        cur.execute(
            "SELECT COUNT(*) AS c FROM users WHERE joined_at IS NOT NULL AND date(joined_at) >= date('now', '-29 days')"
        )
        month = cur.fetchone()["c"]
        conn.close()
        return {"total": total, "today": today, "week": week, "month": month}

    # ---- menu buttons ----

    def get_buttons(self, parent_id):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM menu_buttons WHERE parent_id=? ORDER BY order_index, id",
            (parent_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def get_button(self, button_id):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM menu_buttons WHERE id=?", (button_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_button_by_title_parent(self, title, parent_id):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM menu_buttons WHERE title=? AND parent_id=?",
            (title, parent_id),
        )
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def add_button(self, title, parent_id):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(MAX(order_index), -1) AS m FROM menu_buttons WHERE parent_id=?",
            (parent_id,),
        )
        next_order = cur.fetchone()["m"] + 1
        cur.execute(
            "INSERT INTO menu_buttons (title, parent_id, order_index) VALUES (?, ?, ?)",
            (title, parent_id, next_order),
        )
        conn.commit()
        new_id = cur.lastrowid
        conn.close()
        return new_id

    def rename_button(self, button_id, new_title):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("UPDATE menu_buttons SET title=? WHERE id=?", (new_title, button_id))
        conn.commit()
        conn.close()

    def delete_button(self, button_id):
        conn = self.conn()
        self._delete_button_recursive(conn, button_id)
        conn.commit()
        conn.close()

    def _delete_button_recursive(self, conn, button_id):
        cur = conn.cursor()
        cur.execute("SELECT id FROM menu_buttons WHERE parent_id=?", (button_id,))
        children = [r["id"] for r in cur.fetchall()]
        for child_id in children:
            self._delete_button_recursive(conn, child_id)
        cur.execute("DELETE FROM catalogs WHERE button_id=?", (button_id,))
        cur.execute("DELETE FROM menu_buttons WHERE id=?", (button_id,))

    def move_button(self, button_id, direction):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM menu_buttons WHERE id=?", (button_id,))
        current = cur.fetchone()
        if not current:
            conn.close()
            return
        parent_id = current["parent_id"]
        order_index = current["order_index"]
        if direction == "up":
            cur.execute(
                "SELECT * FROM menu_buttons WHERE parent_id=? AND order_index < ? ORDER BY order_index DESC LIMIT 1",
                (parent_id, order_index),
            )
        else:
            cur.execute(
                "SELECT * FROM menu_buttons WHERE parent_id=? AND order_index > ? ORDER BY order_index ASC LIMIT 1",
                (parent_id, order_index),
            )
        neighbor = cur.fetchone()
        if neighbor:
            cur.execute("UPDATE menu_buttons SET order_index=? WHERE id=?", (neighbor["order_index"], current["id"]))
            cur.execute("UPDATE menu_buttons SET order_index=? WHERE id=?", (order_index, neighbor["id"]))
            conn.commit()
        conn.close()

    # ---- catalogs (content) ----

    def add_catalog_file(self, button_id, file_id, file_name, note, file_type):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO catalogs (button_id, file_id, file_name, note, file_type, uploaded_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (button_id, file_id, file_name, note, file_type),
        )
        conn.commit()
        new_id = cur.lastrowid
        conn.close()
        return new_id

    def get_catalogs(self, button_id):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM catalogs WHERE button_id=? ORDER BY id", (button_id,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def get_catalog_by_id(self, item_id):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM catalogs WHERE id=?", (item_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def delete_catalog(self, item_id):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM catalogs WHERE id=?", (item_id,))
        conn.commit()
        conn.close()

    def get_section_breakdown(self):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT mb.title AS title, COUNT(c.id) AS count
            FROM menu_buttons mb
            LEFT JOIN catalogs c ON c.button_id = mb.id
            GROUP BY mb.id
            ORDER BY mb.parent_id, mb.order_index
        """)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    # ---- search ----

    def search(self, query):
        like = f"%{query}%"
        conn = self.conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, title, parent_id FROM menu_buttons WHERE title LIKE ? ORDER BY title LIMIT 30",
            (like,),
        )
        buttons = [dict(r) for r in cur.fetchall()]
        cur.execute(
            "SELECT id, button_id, file_name, note, file_type FROM catalogs "
            "WHERE note LIKE ? OR file_name LIKE ? ORDER BY id DESC LIMIT 30",
            (like, like),
        )
        contents = [dict(r) for r in cur.fetchall()]
        conn.close()
        return buttons, contents

    # ---- settings ----

    def set_setting(self, key, value):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        conn.commit()
        conn.close()

    def get_setting(self, key, default=None):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
        conn.close()
        if row is None:
            return default
        return row["value"]

    # ---- activity log ----

    def log_activity(self, admin_id, admin_name, action, details=""):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO activity_log (admin_id, admin_name, action, details) VALUES (?, ?, ?, ?)",
            (admin_id, admin_name, action, details),
        )
        conn.commit()
        conn.close()

    def get_recent_activity(self, limit=20):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT admin_id, admin_name, action, details, created_at FROM activity_log "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    # ---- stats ----

    def get_stats(self):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS c FROM users")
        users = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM menu_buttons")
        buttons = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM catalogs")
        catalogs = cur.fetchone()["c"]
        conn.close()
        return {"users": users, "buttons": buttons, "catalogs": catalogs}

    # ---- backup / restore ----

    def backup_to_file(self, target_path):
        src = self.conn()
        dst = sqlite3.connect(target_path)
        with dst:
            src.backup(dst)
        dst.close()
        src.close()

    def restore_from_file(self, source_path):
        with open(source_path, "rb") as f:
            header = f.read(16)
        if not header.startswith(b"SQLite format 3"):
            raise ValueError("فایل ارسالی یک دیتابیس معتبر SQLite نیست.")

        backup_path = DB_PATH + ".pre_restore_backup"
        if os.path.exists(DB_PATH):
            shutil.copy2(DB_PATH, backup_path)

        shutil.copy2(source_path, DB_PATH)
        self.init_db()
