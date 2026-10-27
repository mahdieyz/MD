import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", "data/bot.db")


# Default tree seeded on first boot: (title, legacy_key, children)
DEFAULT_TREE = [
    ("مگنتار و چراغ لاینی", "magnetar_line", []),
    ("کلید ، پریز هوشمند و مکانیکی", "switches_group", [
        ("پریز و کلید هوشمند", "smart_switches", []),
        ("کلید مکانیکی", "mechanical_switches", []),
    ]),
    ("صنعتی ساختمانی", "industrial", []),
    ("نمای ساختمان - محوطه - استخری", "facade_group", [
        ("مد نور", "mod_noor", []),
        ("شعاع", "shaa", []),
        ("انوار", "anvar", []),
    ]),
    ("سیم و کابل", "wire_cable", []),
    ("آیفون", "intercom", []),
    ("اعلان حریق", "fire_alarm", []),
    ("پریز کابینتی میلو", "milo_socket", []),
    ("پریز کابینتی ملونی", "meloni_socket", []),
]


class Database:
    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        self.legacy_map = {}
        self.init_db()

    # ------------------------------------------------------------------
    # Connection / schema
    # ------------------------------------------------------------------
    def conn(self):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _table_exists(self, cur, name):
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
        return cur.fetchone() is not None

    def _column_exists(self, cur, table, column):
        cur.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in cur.fetchall())

    def init_db(self):
        with self.conn() as conn:
            cur = conn.cursor()

            if not self._table_exists(cur, "users"):
                cur.execute("""
                    CREATE TABLE users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        joined_at TEXT
                    )
                """)
            elif not self._column_exists(cur, "users", "joined_at"):
                cur.execute("ALTER TABLE users ADD COLUMN joined_at TEXT")

            if not self._table_exists(cur, "settings"):
                cur.execute("""
                    CREATE TABLE settings (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """)

            if not self._table_exists(cur, "menu_buttons"):
                cur.execute("""
                    CREATE TABLE menu_buttons (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        parent_id INTEGER NOT NULL DEFAULT 0,
                        title TEXT NOT NULL,
                        position INTEGER NOT NULL DEFAULT 0
                    )
                """)
            else:
                # Migration: legacy schema used "order_index" instead of "position".
                if not self._column_exists(cur, "menu_buttons", "position"):
                    cur.execute(
                        "ALTER TABLE menu_buttons ADD COLUMN position INTEGER NOT NULL DEFAULT 0"
                    )
                    if self._column_exists(cur, "menu_buttons", "order_index"):
                        cur.execute(
                            "UPDATE menu_buttons SET position = order_index"
                        )

            if not self._table_exists(cur, "catalogs"):
                cur.execute("""
                    CREATE TABLE catalogs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        button_id INTEGER NOT NULL DEFAULT 0,
                        file_id TEXT,
                        file_name TEXT,
                        note TEXT,
                        file_type TEXT NOT NULL,
                        category_key TEXT,
                        uploaded_at TEXT DEFAULT (datetime('now'))
                    )
                """)
            else:
                # Defensive migration for legacy catalogs schema variants.
                if not self._column_exists(cur, "catalogs", "button_id"):
                    cur.execute("ALTER TABLE catalogs ADD COLUMN button_id INTEGER NOT NULL DEFAULT 0")
                if not self._column_exists(cur, "catalogs", "file_type"):
                    cur.execute("ALTER TABLE catalogs ADD COLUMN file_type TEXT DEFAULT 'document'")
                if not self._column_exists(cur, "catalogs", "category_key"):
                    cur.execute("ALTER TABLE catalogs ADD COLUMN category_key TEXT")
                if not self._column_exists(cur, "catalogs", "uploaded_at"):
                    cur.execute("ALTER TABLE catalogs ADD COLUMN uploaded_at TEXT DEFAULT (datetime('now'))")

            if not self._table_exists(cur, "activity_log"):
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

        if self._count_menu_buttons() == 0:
            self._seed_defaults()

        self._build_legacy_map()
        self._migrate_legacy_catalogs()

    def _count_menu_buttons(self):
        with self.conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM menu_buttons")
            return cur.fetchone()[0]

    def _seed_defaults(self):
        with self.conn() as conn:
            cur = conn.cursor()

            def insert_tree(parent_id, nodes):
                for pos, (title, key, children) in enumerate(nodes):
                    cur.execute(
                        "INSERT INTO menu_buttons (parent_id, title, position) VALUES (?, ?, ?)",
                        (parent_id, title, pos),
                    )
                    button_id = cur.lastrowid
                    insert_tree(button_id, children)

            insert_tree(0, DEFAULT_TREE)
            conn.commit()

    # ------------------------------------------------------------------
    # Legacy key migration (old category_key rows -> button_id)
    # ------------------------------------------------------------------
    def _build_legacy_map(self):
        self.legacy_map = {}
        with self.conn() as conn:
            cur = conn.cursor()
            if self._column_exists(cur, "menu_buttons", "legacy_key"):
                cur.execute(
                    "SELECT id, legacy_key FROM menu_buttons "
                    "WHERE legacy_key IS NOT NULL AND legacy_key != ''"
                )
                for row in cur.fetchall():
                    self.legacy_map[row["legacy_key"]] = row["id"]

    def _migrate_legacy_catalogs(self):
        with self.conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, category_key FROM catalogs WHERE button_id = 0 AND category_key IS NOT NULL"
            )
            rows = cur.fetchall()
            changed = False
            for row in rows:
                button_id = self.legacy_map.get(row["category_key"])
                if button_id:
                    cur.execute(
                        "UPDATE catalogs SET button_id = ? WHERE id = ?",
                        (button_id, row["id"]),
                    )
                    changed = True
            if changed:
                conn.commit()

    def reset_menu(self):
        with self.conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM catalogs")
            cur.execute("DELETE FROM menu_buttons")
            conn.commit()
        self.init_db()

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    def add_user(self, user_id, username, first_name):
        with self.conn() as conn:
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

    def get_all_users(self):
        with self.conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM users")
            return cur.fetchall()

    def get_user_growth_stats(self):
        with self.conn() as conn:
            cur = conn.cursor()
            stats = {"total": 0, "today": 0, "week": 0, "month": 0}
            cur.execute("SELECT COUNT(*) FROM users")
            stats["total"] = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(*) FROM users WHERE joined_at IS NOT NULL AND joined_at >= date('now')"
            )
            stats["today"] = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(*) FROM users WHERE joined_at IS NOT NULL AND joined_at >= date('now', '-6 days')"
            )
            stats["week"] = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(*) FROM users WHERE joined_at IS NOT NULL AND joined_at >= date('now', '-29 days')"
            )
            stats["month"] = cur.fetchone()[0]
            return stats

    # ------------------------------------------------------------------
    # Menu buttons
    # ------------------------------------------------------------------
    def get_buttons(self, parent_id):
        with self.conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM menu_buttons WHERE parent_id = ? ORDER BY position, id",
                (parent_id,),
            )
            return cur.fetchall()

    def get_button(self, button_id):
        with self.conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM menu_buttons WHERE id = ?", (button_id,))
            return cur.fetchone()

    def get_button_by_title_parent(self, title, parent_id):
        with self.conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM menu_buttons WHERE title = ? AND parent_id = ?",
                (title, parent_id),
            )
            return cur.fetchone()

    def add_button(self, parent_id, title):
        with self.conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM menu_buttons WHERE parent_id = ?",
                (parent_id,),
            )
            next_pos = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO menu_buttons (parent_id, title, position) VALUES (?, ?, ?)",
                (parent_id, title, next_pos),
            )
            new_id = cur.lastrowid
            conn.commit()
            return new_id

    def rename_button(self, button_id, title):
        with self.conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE menu_buttons SET title = ? WHERE id = ?", (title, button_id))
            conn.commit()

    def delete_button(self, button_id):
        with self.conn() as conn:
            cur = conn.cursor()
            self._delete_button_recursive(cur, button_id)
            conn.commit()

    def _delete_button_recursive(self, cur, button_id):
        cur.execute("SELECT id FROM menu_buttons WHERE parent_id = ?", (button_id,))
        children = cur.fetchall()
        for child in children:
            self._delete_button_recursive(cur, child["id"])
        cur.execute("DELETE FROM catalogs WHERE button_id = ?", (button_id,))
        cur.execute("DELETE FROM menu_buttons WHERE id = ?", (button_id,))

    def move_button(self, button_id, direction):
        with self.conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM menu_buttons WHERE id = ?", (button_id,))
            btn = cur.fetchone()
            if not btn:
                return
            if direction < 0:
                cur.execute(
                    "SELECT * FROM menu_buttons WHERE parent_id = ? AND position < ? ORDER BY position DESC, id DESC LIMIT 1",
                    (btn["parent_id"], btn["position"]),
                )
            else:
                cur.execute(
                    "SELECT * FROM menu_buttons WHERE parent_id = ? AND position > ? ORDER BY position ASC, id ASC LIMIT 1",
                    (btn["parent_id"], btn["position"]),
                )
            neighbor = cur.fetchone()
            if not neighbor:
                return
            cur.execute("UPDATE menu_buttons SET position = ? WHERE id = ?", (neighbor["position"], btn["id"]))
            cur.execute("UPDATE menu_buttons SET position = ? WHERE id = ?", (btn["position"], neighbor["id"]))
            conn.commit()

    # ------------------------------------------------------------------
    # Catalog content
    # ------------------------------------------------------------------
    def add_catalog_file(self, button_id, file_id, file_name, note, file_type, category_key=None):
        with self.conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO catalogs (button_id, file_id, file_name, note, file_type, category_key)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (button_id, file_id, file_name, note, file_type, category_key),
            )
            new_id = cur.lastrowid
            conn.commit()
            return new_id

    def get_catalogs(self, button_id):
        with self.conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM catalogs WHERE button_id = ? ORDER BY id", (button_id,))
            return cur.fetchall()

    def get_catalog_by_id(self, catalog_id):
        with self.conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM catalogs WHERE id = ?", (catalog_id,))
            return cur.fetchone()

    def delete_catalog(self, catalog_id):
        with self.conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM catalogs WHERE id = ?", (catalog_id,))
            conn.commit()

    def get_section_breakdown(self):
        with self.conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT mb.title, COUNT(c.id) AS cnt
                FROM menu_buttons mb
                LEFT JOIN catalogs c ON c.button_id = mb.id
                GROUP BY mb.id
                ORDER BY cnt DESC
            """)
            return cur.fetchall()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def search(self, query):
        like = f"%{query}%"
        with self.conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM menu_buttons WHERE title LIKE ? ORDER BY id LIMIT 30",
                (like,),
            )
            buttons = cur.fetchall()
            cur.execute(
                "SELECT * FROM catalogs WHERE note LIKE ? OR file_name LIKE ? ORDER BY id LIMIT 30",
                (like, like),
            )
            contents = cur.fetchall()
            return buttons, contents

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def set_setting(self, key, value):
        with self.conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            conn.commit()

    def get_setting(self, key):
        with self.conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cur.fetchone()
            return row["value"] if row else None

    # ------------------------------------------------------------------
    # Activity log
    # ------------------------------------------------------------------
    def log_activity(self, admin_id, admin_name, action, details=""):
        with self.conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO activity_log (admin_id, admin_name, action, details) VALUES (?, ?, ?, ?)",
                (admin_id, admin_name, action, details),
            )
            conn.commit()

    def get_recent_activity(self, limit=20):
        with self.conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM activity_log ORDER BY id DESC LIMIT ?", (limit,))
            return cur.fetchall()

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------
    def get_stats(self):
        with self.conn() as conn:
            cur = conn.cursor()
            stats = {"users": 0, "buttons": 0, "catalogs": 0}
            cur.execute("SELECT COUNT(*) FROM users")
            stats["users"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM menu_buttons")
            stats["buttons"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM catalogs")
            stats["catalogs"] = cur.fetchone()[0]
            return stats

    # ------------------------------------------------------------------
    # Backup / restore
    # ------------------------------------------------------------------
    def backup_to_file(self, target_path):
        src = sqlite3.connect(DB_PATH)
        dst = sqlite3.connect(target_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()

    def restore_from_file(self, source_path):
        with open(source_path, "rb") as f:
            header = f.read(16)
        if not header.startswith(b"SQLite format 3"):
            raise ValueError("Invalid database file")

        pre_restore = DB_PATH + ".pre_restore_backup"
        self.backup_to_file(pre_restore)

        os.replace(source_path, DB_PATH)
        for suffix in ("-wal", "-shm"):
            side = DB_PATH + suffix
            if os.path.exists(side):
                os.remove(side)

        self.init_db()
