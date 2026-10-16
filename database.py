import os, shutil, logging, sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)
DB_PATH = os.getenv("DB_PATH", "bot_database.db")


class Database:
    def __init__(self):
        self.db_name = DB_PATH
        db_dir = os.path.dirname(self.db_name)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logging.info(f"📁 Created DB directory: {db_dir}")
        self.init_db()

    def conn(self):
        c = sqlite3.connect(self.db_name)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL;")
        return c

    # --- helpers ---
    def _table_exists(self, c, name):
        return c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone() is not None

    def _column_exists(self, c, table, col):
        info = c.execute(f"PRAGMA table_info({table})").fetchall()
        return any(r["name"] == col for r in info)

    # --- schema + migration (safe to call again after a restore) ---
    def init_db(self):
        c = self.conn()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, username TEXT,
                first_name TEXT, last_name TEXT,
                join_date TEXT, last_activity TEXT
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, value TEXT
            );
            CREATE TABLE IF NOT EXISTS menu_buttons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id INTEGER DEFAULT 0,
                title TEXT NOT NULL,
                order_index INTEGER DEFAULT 0,
                legacy_key TEXT
            );
        """)

        if not self._table_exists(c, "catalogs"):
            c.execute("""
                CREATE TABLE catalogs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    button_id INTEGER,
                    category_key TEXT,
                    title TEXT,
                    file_id TEXT,
                    file_name TEXT,
                    file_type TEXT DEFAULT 'document',
                    note TEXT,
                    created_at TEXT
                )
            """)
        else:
            if not self._column_exists(c, "catalogs", "button_id"):
                c.execute("ALTER TABLE catalogs ADD COLUMN button_id INTEGER")
            if not self._column_exists(c, "catalogs", "file_type"):
                c.execute("ALTER TABLE catalogs ADD COLUMN file_type TEXT DEFAULT 'document'")

        c.commit()
        self._seed_defaults(c)

        # انتقال فایل‌های قدیمی که فقط با category_key متنی ذخیره شده بودند
        if self._column_exists(c, "catalogs", "category_key"):
            rows = c.execute(
                "SELECT id, category_key FROM catalogs WHERE button_id IS NULL AND category_key IS NOT NULL"
            ).fetchall()
            for r in rows:
                btn = c.execute(
                    "SELECT id FROM menu_buttons WHERE legacy_key=?", (r["category_key"],)
                ).fetchone()
                if btn:
                    c.execute("UPDATE catalogs SET button_id=? WHERE id=?", (btn["id"], r["id"]))

        c.commit()
        c.close()

    def _seed_defaults(self, c):
        count = c.execute("SELECT COUNT(*) FROM menu_buttons").fetchone()[0]
        if count > 0:
            return

        def ins(title, parent_id, legacy_key=None, order_index=0):
            c.execute(
                "INSERT INTO menu_buttons (parent_id, title, order_index, legacy_key) VALUES (?,?,?,?)",
                (parent_id, title, order_index, legacy_key),
            )
            return c.lastrowid

        ins("مگنتار و چراغ لاینی", 0, "magnetar_line", 0)
        switches = ins("کلید ، پریز هوشمند و مکانیکی", 0, None, 1)
        ins("صنعتی ساختمانی", 0, "industrial", 2)
        facade = ins("نمای ساختمان - محوطه - استخری", 0, None, 3)
        ins("سیم و کابل", 0, "wire_cable", 4)
        ins("آیفون", 0, "intercom", 5)
        ins("اعلان حریق", 0, "fire_alarm", 6)
        ins("پریز کابینتی میلو", 0, "milo_socket", 7)
        ins("پریز کابینتی ملونی", 0, "meloni_socket", 8)

        ins("پریز و کلید هوشمند", switches, "smart_switches", 0)
        ins("کلید مکانیکی", switches, "mechanical_switches", 1)

        ins("مد نور", facade, "mod_noor", 0)
        ins("شعاع", facade, "shaa", 1)
        ins("انوار", facade, "anvar", 2)

        c.commit()

    def reset_menu(self):
        """بازنشانی فقط منو و فایل‌ها (تنظیمات/کاربران دست‌نخورده باقی می‌مانند)"""
        c = self.conn()
        try:
            c.execute("DELETE FROM catalogs;")
            c.execute("DELETE FROM menu_buttons;")
            c.commit()
            self._seed_defaults(c)
            c.commit()
            return True
        except Exception as e:
            c.rollback()
            logger.error(f"Menu reset error: {e}")
            return False
        finally:
            c.close()

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

    # ── MENU BUTTONS (ویرایشگر منو) ──
    def get_buttons(self, parent_id=0):
        c = self.conn()
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM menu_buttons WHERE parent_id=? ORDER BY order_index, id", (parent_id,)
        ).fetchall()]
        c.close(); return rows

    def get_button(self, button_id):
        c = self.conn()
        r = c.execute("SELECT * FROM menu_buttons WHERE id=?", (button_id,)).fetchone()
        c.close(); return dict(r) if r else None

    def get_button_by_title_parent(self, title, parent_id):
        c = self.conn()
        r = c.execute(
            "SELECT * FROM menu_buttons WHERE title=? AND parent_id=?", (title, parent_id)
        ).fetchone()
        c.close(); return dict(r) if r else None

    def add_button(self, title, parent_id=0):
        c = self.conn()
        max_idx = c.execute(
            "SELECT COALESCE(MAX(order_index),-1) FROM menu_buttons WHERE parent_id=?", (parent_id,)
        ).fetchone()[0]
        c.execute(
            "INSERT INTO menu_buttons (parent_id, title, order_index) VALUES (?,?,?)",
            (parent_id, title, max_idx + 1))
        c.commit(); bid = c.lastrowid; c.close()
        return bid

    def rename_button(self, button_id, new_title):
        c = self.conn()
        c.execute("UPDATE menu_buttons SET title=? WHERE id=?", (new_title, button_id))
        c.commit(); c.close()

    def delete_button(self, button_id):
        c = self.conn()

        def collect(bid):
            ids = [bid]
            for ch in c.execute("SELECT id FROM menu_buttons WHERE parent_id=?", (bid,)).fetchall():
                ids.extend(collect(ch["id"]))
            return ids

        ids = collect(button_id)
        qs = ",".join("?" * len(ids))
        c.execute(f"DELETE FROM catalogs WHERE button_id IN ({qs})", ids)
        c.execute(f"DELETE FROM menu_buttons WHERE id IN ({qs})", ids)
        c.commit(); c.close()

    def move_button(self, button_id, direction):
        """direction: 'up' یا 'down' — جابجایی با دکمه هم‌سطح مجاور"""
        c = self.conn()
        btn = c.execute("SELECT * FROM menu_buttons WHERE id=?", (button_id,)).fetchone()
        if not btn:
            c.close(); return False
        siblings = c.execute(
            "SELECT * FROM menu_buttons WHERE parent_id=? ORDER BY order_index, id",
            (btn["parent_id"],)
        ).fetchall()
        idx = next((i for i, s in enumerate(siblings) if s["id"] == button_id), None)
        if idx is None:
            c.close(); return False
        swap_idx = idx - 1 if direction == "up" else idx + 1
        if swap_idx < 0 or swap_idx >= len(siblings):
            c.close(); return False
        a, b = siblings[idx], siblings[swap_idx]
        c.execute("UPDATE menu_buttons SET order_index=? WHERE id=?", (b["order_index"], a["id"]))
        c.execute("UPDATE menu_buttons SET order_index=? WHERE id=?", (a["order_index"], b["id"]))
        c.commit(); c.close()
        return True

    # ── CATALOGS / FILES ──
    def add_catalog_file(self, button_id, file_id, file_name="", note="", file_type="document"):
        c = self.conn()
        c.execute(
            "INSERT INTO catalogs (button_id, file_id, file_name, file_type, note, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (button_id, file_id, file_name, file_type, note, datetime.now().isoformat()))
        c.commit(); c.close()

    def get_catalogs(self, button_id):
        c = self.conn()
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM catalogs WHERE button_id=? ORDER BY id ASC", (button_id,)
        ).fetchall()]
        c.close(); return rows

    def get_catalog_by_id(self, cat_id):
        c = self.conn()
        r = c.execute("SELECT * FROM catalogs WHERE id=?", (cat_id,)).fetchone()
        c.close(); return dict(r) if r else None

    def delete_catalog(self, cat_id):
        c = self.conn()
        c.execute("DELETE FROM catalogs WHERE id=?", (cat_id,))
        c.commit(); c.close()

    def get_section_breakdown(self):
        """تعداد فایل در هر بخش که حداقل یک فایل دارد"""
        c = self.conn()
        rows = c.execute("""
            SELECT m.title as title, COUNT(c.id) as cnt
            FROM catalogs c JOIN menu_buttons m ON m.id = c.button_id
            GROUP BY c.button_id ORDER BY cnt DESC
        """).fetchall()
        c.close()
        return [(r["title"], r["cnt"]) for r in rows]

    # ── SETTINGS ──
    def set_setting(self, key, val):
        c = self.conn()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, val))
        c.commit(); c.close()

    def get_setting(self, key, default=""):
        c = self.conn()
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        c.close(); return r["value"] if r and r["value"] else default

    # ── STATS ──
    def get_stats(self):
        c = self.conn()
        u = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        f = c.execute("SELECT COUNT(*) FROM catalogs").fetchone()[0]
        b = c.execute("SELECT COUNT(*) FROM menu_buttons").fetchone()[0]
        c.close()
        return {"total_users": u, "total_files": f, "total_buttons": b}

    # ── BACKUP / RESTORE ──
    def backup_to_file(self, target_path):
        """Safe backup using SQLite's online backup API."""
        src = sqlite3.connect(self.db_name)
        dst = sqlite3.connect(target_path)
        with dst:
            src.backup(dst)
        dst.close(); src.close()
        return target_path

    def restore_from_file(self, source_path):
        """Validate and restore from a .db file. Returns True on success."""
        try:
            test = sqlite3.connect(source_path)
            test.execute("SELECT name FROM sqlite_master WHERE type='table'")
            test.close()

            if os.path.exists(self.db_name):
                self.backup_to_file(self.db_name + ".pre_restore_backup")

            shutil.copy2(source_path, self.db_name)

            # نکته‌ی مهم: اگر بکاپ مربوط به نسخه‌ی قدیمی ربات باشد (بدون جدول
            # منوی پویا)، باید migration دوباره اجرا شود تا ربات کرش نکند.
            self.init_db()
            return True
        except Exception as e:
            logging.error(f"Restore failed: {e}")
            return False
