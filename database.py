import os
import sqlite3
import shutil
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "data/bot.db")


class Database:
    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        self.init_db()

    def conn(self):
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # ---------- schema helpers ----------
    def _table_exists(self, cur, table):
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        return cur.fetchone() is not None

    def _column_exists(self, cur, table, column):
        cur.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in cur.fetchall())

    # ---------- init / migration ----------
    def init_db(self):
        conn = self.conn()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

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
                legacy_key TEXT,
                order_index INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # catalogs table: create fresh or migrate old schema
        if not self._table_exists(cur, "catalogs"):
            cur.execute("""
                CREATE TABLE catalogs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    button_id INTEGER NOT NULL DEFAULT 0,
                    file_id TEXT NOT NULL,
                    file_name TEXT,
                    note TEXT,
                    file_type TEXT NOT NULL DEFAULT 'document',
                    category_key TEXT,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        else:
            if not self._column_exists(cur, "catalogs", "button_id"):
                cur.execute("ALTER TABLE catalogs ADD COLUMN button_id INTEGER NOT NULL DEFAULT 0")
            if not self._column_exists(cur, "catalogs", "file_type"):
                cur.execute("ALTER TABLE catalogs ADD COLUMN file_type TEXT NOT NULL DEFAULT 'document'")
            if not self._column_exists(cur, "catalogs", "category_key"):
                cur.execute("ALTER TABLE catalogs ADD COLUMN category_key TEXT")
            if not self._column_exists(cur, "catalogs", "note"):
                cur.execute("ALTER TABLE catalogs ADD COLUMN note TEXT")

        conn.commit()

        self._seed_defaults(conn)
        self._migrate_legacy_catalogs(conn)

        conn.commit()
        conn.close()

    def _seed_defaults(self, conn):
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM menu_buttons")
        if cur.fetchone()[0] > 0:
            return  # already seeded, never re-seed

        def ins(title, parent_id, legacy_key, order_index):
            cur.execute(
                "INSERT INTO menu_buttons (title, parent_id, legacy_key, order_index) VALUES (?, ?, ?, ?)",
                (title, parent_id, legacy_key, order_index),
            )
            return cur.lastrowid

        idx = 0

        ins("مگنتار و چراغ لاینی", 0, "magnetar_line", idx); idx += 1

        smart_group_id = ins("کلید ، پریز هوشمند و مکانیکی", 0, None, idx); idx += 1
        ins("پریز و کلید هوشمند", smart_group_id, "smart_switches", 0)
        ins("کلید مکانیکی", smart_group_id, "mechanical_switches", 1)

        ins("صنعتی ساختمانی", 0, "industrial", idx); idx += 1

        facade_group_id = ins("نمای ساختمان - محوطه - استخری", 0, None, idx); idx += 1
        ins("مد نور", facade_group_id, "mod_noor", 0)
        ins("شعاع", facade_group_id, "shaa", 1)
        ins("انوار", facade_group_id, "anvar", 2)

        ins("سیم و کابل", 0, "wire_cable", idx); idx += 1
        ins("آیفون", 0, "intercom", idx); idx += 1
        ins("اعلان حریق", 0, "fire_alarm", idx); idx += 1
        ins("پریز کابینتی میلو", 0, "milo_socket", idx); idx += 1
        ins("پریز کابینتی ملونی", 0, "meloni_socket", idx); idx += 1

        conn.commit()

    def _migrate_legacy_catalogs(self, conn):
        cur = conn.cursor()
        if not self._column_exists(cur, "catalogs", "category_key"):
            return

        cur.execute(
            "SELECT id, category_key FROM catalogs "
            "WHERE category_key IS NOT NULL AND category_key != '' AND (button_id IS NULL OR button_id = 0)"
        )
        rows = cur.fetchall()
        if not rows:
            return

        cur.execute("SELECT id, legacy_key FROM menu_buttons WHERE legacy_key IS NOT NULL")
        key_map = {legacy_key: bid for bid, legacy_key in cur.fetchall()}

        for cat_id, category_key in rows:
            bid = key_map.get(category_key)
            if bid:
                cur.execute("UPDATE catalogs SET button_id = ? WHERE id = ?", (bid, cat_id))

        conn.commit()

    # ---------- scoped reset ----------
    def reset_menu(self):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM catalogs")
        cur.execute("DELETE FROM menu_buttons")
        conn.commit()
        conn.close()
        # re-init fresh
        self.init_db()

    # ---------- users ----------
    def add_user(self, user_id, username, first_name):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name
        """, (user_id, username, first_name))
        conn.commit()
        conn.close()

    def get_all_users(self):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users")
        rows = [r[0] for r in cur.fetchall()]
        conn.close()
        return rows

    # ---------- menu tree ----------
    def get_buttons(self, parent_id=0):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, title, parent_id, legacy_key, order_index FROM menu_buttons "
            "WHERE parent_id = ? ORDER BY order_index ASC, id ASC",
            (parent_id,),
        )
        rows = cur.fetchall()
        conn.close()
        return [
            {"id": r[0], "title": r[1], "parent_id": r[2], "legacy_key": r[3], "order_index": r[4]}
            for r in rows
        ]

    def get_button(self, button_id):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, title, parent_id, legacy_key, order_index FROM menu_buttons WHERE id = ?",
            (button_id,),
        )
        r = cur.fetchone()
        conn.close()
        if not r:
            return None
        return {"id": r[0], "title": r[1], "parent_id": r[2], "legacy_key": r[3], "order_index": r[4]}

    def get_button_by_title_parent(self, title, parent_id):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, title, parent_id, legacy_key, order_index FROM menu_buttons "
            "WHERE title = ? AND parent_id = ?",
            (title, parent_id),
        )
        r = cur.fetchone()
        conn.close()
        if not r:
            return None
        return {"id": r[0], "title": r[1], "parent_id": r[2], "legacy_key": r[3], "order_index": r[4]}

    def add_button(self, title, parent_id):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(order_index), -1) + 1 FROM menu_buttons WHERE parent_id = ?", (parent_id,))
        next_idx = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO menu_buttons (title, parent_id, legacy_key, order_index) VALUES (?, ?, NULL, ?)",
            (title, parent_id, next_idx),
        )
        new_id = cur.lastrowid
        conn.commit()
        conn.close()
        return new_id

    def rename_button(self, button_id, new_title):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("UPDATE menu_buttons SET title = ? WHERE id = ?", (new_title, button_id))
        conn.commit()
        conn.close()

    def delete_button(self, button_id):
        conn = self.conn()
        cur = conn.cursor()

        def recurse(bid):
            cur.execute("SELECT id FROM menu_buttons WHERE parent_id = ?", (bid,))
            for (child_id,) in cur.fetchall():
                recurse(child_id)
            cur.execute("DELETE FROM catalogs WHERE button_id = ?", (bid,))
            cur.execute("DELETE FROM menu_buttons WHERE id = ?", (bid,))

        recurse(button_id)
        conn.commit()
        conn.close()

    def move_button(self, button_id, direction):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT parent_id, order_index FROM menu_buttons WHERE id = ?", (button_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return
        parent_id, order_index = row

        if direction == "up":
            cur.execute(
                "SELECT id, order_index FROM menu_buttons WHERE parent_id = ? AND order_index < ? "
                "ORDER BY order_index DESC LIMIT 1",
                (parent_id, order_index),
            )
        else:
            cur.execute(
                "SELECT id, order_index FROM menu_buttons WHERE parent_id = ? AND order_index > ? "
                "ORDER BY order_index ASC LIMIT 1",
                (parent_id, order_index),
            )
        neighbor = cur.fetchone()
        if neighbor:
            neighbor_id, neighbor_idx = neighbor
            cur.execute("UPDATE menu_buttons SET order_index = ? WHERE id = ?", (neighbor_idx, button_id))
            cur.execute("UPDATE menu_buttons SET order_index = ? WHERE id = ?", (order_index, neighbor_id))
            conn.commit()
        conn.close()

    # ---------- catalogs / files ----------
    def add_catalog_file(self, button_id, file_id, file_name, note, file_type):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO catalogs (button_id, file_id, file_name, note, file_type) VALUES (?, ?, ?, ?, ?)",
            (button_id, file_id, file_name, note, file_type),
        )
        new_id = cur.lastrowid
        conn.commit()
        conn.close()
        return new_id

    def get_catalogs(self, button_id):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, button_id, file_id, file_name, note, file_type FROM catalogs "
            "WHERE button_id = ? ORDER BY id ASC",
            (button_id,),
        )
        rows = cur.fetchall()
        conn.close()
        return [
            {"id": r[0], "button_id": r[1], "file_id": r[2], "file_name": r[3], "note": r[4], "file_type": r[5]}
            for r in rows
        ]

    def get_catalog_by_id(self, catalog_id):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, button_id, file_id, file_name, note, file_type FROM catalogs WHERE id = ?",
            (catalog_id,),
        )
        r = cur.fetchone()
        conn.close()
        if not r:
            return None
        return {"id": r[0], "button_id": r[1], "file_id": r[2], "file_name": r[3], "note": r[4], "file_type": r[5]}

    def delete_catalog(self, catalog_id):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM catalogs WHERE id = ?", (catalog_id,))
        conn.commit()
        conn.close()

    def get_section_breakdown(self):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT COALESCE(mb.title, 'عمومی (ریشه)') AS title, COUNT(c.id) AS cnt
            FROM catalogs c
            LEFT JOIN menu_buttons mb ON mb.id = c.button_id
            GROUP BY c.button_id
            ORDER BY cnt DESC
        """)
        rows = cur.fetchall()
        conn.close()
        return [{"title": r[0], "count": r[1]} for r in rows]

    # ---------- settings ----------
    def set_setting(self, key, value):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        conn.commit()
        conn.close()

    def get_setting(self, key, default=None):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
        r = cur.fetchone()
        conn.close()
        return r[0] if r else default

    # ---------- stats ----------
    def get_stats(self):
        conn = self.conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        users = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM catalogs")
        files = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM menu_buttons")
        buttons = cur.fetchone()[0]
        conn.close()
        return {"users": users, "files": files, "buttons": buttons}

    # ---------- backup / restore ----------
    def backup_to_file(self, target_path):
        os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
        src = self.conn()
        dst = sqlite3.connect(target_path)
        with dst:
            src.backup(dst)
        dst.close()
        src.close()
        return target_path

    def restore_from_file(self, source_path):
        # validate it's a real sqlite db
        with open(source_path, "rb") as f:
            header = f.read(16)
        if not header.startswith(b"SQLite format 3"):
            raise ValueError("فایل آپلودشده یک دیتابیس SQLite معتبر نیست.")

        if os.path.exists(DB_PATH):
            backup_path = DB_PATH + ".pre_restore_backup"
            shutil.copy2(DB_PATH, backup_path)

        shutil.copy2(source_path, DB_PATH)

        # re-run migrations in case the restored backup is from an older schema
        self.init_db()
        return True
