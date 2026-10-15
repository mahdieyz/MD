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
                join_date TEXT, last_activity TEXT,
                is_premium INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                calculation_count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS calculations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, calc_type TEXT,
                input_data TEXT, result TEXT, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE, persian_name TEXT,
                unit TEXT, price REAL, category TEXT, updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, value TEXT
            );
            CREATE TABLE IF NOT EXISTS est_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                structure TEXT, quality TEXT, price REAL,
                UNIQUE(structure, quality)
            );
        """)
        c.commit(); c.close()
        self._seed()

    def _seed(self):
        c = self.conn()
        now = datetime.now().isoformat()
        mats = [
            ("cement","سیمان","کیسه",85000,"مصالح پایه"),
            ("brick","آجر","عدد",1200,"مصالح پایه"),
            ("sand","شن و ماسه","تن",350000,"مصالح پایه"),
            ("rebar","میلگرد","کیلوگرم",32000,"فلزات"),
            ("steel","فولاد","کیلوگرم",35000,"فلزات"),
            ("concrete","بتن آماده","متر مکعب",1800000,"بتن"),
            ("tile","کاشی","متر مربع",250000,"نازک‌کاری"),
            ("ceramic","سرامیک","متر مربع",300000,"نازک‌کاری"),
            ("paint","رنگ","متر مربع",45000,"نازک‌کاری"),
            ("gypsum","گچ","متر مربع",120000,"نازک‌کاری"),
            ("waterproofing","عایق رطوبتی","متر مربع",180000,"عایق"),
            ("wood","چوب","متر مکعب",8000000,"چوب"),
            ("glass","شیشه","متر مربع",350000,"نازک‌کاری"),
            ("pipe_pvc","لوله PVC","متر",45000,"تاسیسات"),
            ("wire","سیم برق","متر",15000,"تاسیسات"),
            ("door","درب داخلی","عدد",5000000,"در و پنجره"),
            ("window_upvc","پنجره UPVC","متر مربع",3500000,"در و پنجره"),
        ]
        for m in mats:
            c.execute("INSERT OR IGNORE INTO materials (name,persian_name,unit,price,category,updated_at) VALUES (?,?,?,?,?,?)", (*m, now))

        defaults = {
            "welcome_msg": "🏗 *ربات محاسبات ساختمانی*\n\nسلام {name} عزیز! 👋\n\n🔹 محاسبه مصالح ساختمانی\n🔹 برآورد هزینه ساخت\n🔹 قیمت روز مصالح\n🔹 تبدیل واحدها\n\nاز منوی زیر انتخاب کنید: 👇",
            "help_msg": "📖 *راهنما*\n\n🧮 محاسبه‌گر: آجر، بتن، میلگرد، رنگ، کاشی، گچ، عایق، فونداسیون، ستون\n💰 برآورد: تخمین هزینه ساخت\n📦 مصالح: قیمت روز\n📐 تبدیل: متر، فوت، کیلوگرم\n\n⚠️ قیمت‌ها تقریبی هستند.",
        }
        for k, v in defaults.items():
            c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

        est = [
            ("steel","economic",15000000),("steel","medium",22000000),("steel","luxury",35000000),
            ("concrete","economic",16000000),("concrete","medium",23000000),("concrete","luxury",37000000),
            ("masonry","economic",12000000),("masonry","medium",18000000),("masonry","luxury",28000000),
        ]
        for e in est:
            c.execute("INSERT OR IGNORE INTO est_prices (structure,quality,price) VALUES (?,?,?)", e)

        c.commit(); c.close()

    # ── Users ──
    def add_user(self, uid, uname, fname, lname):
        c = self.conn(); now = datetime.now().isoformat()
        c.execute("INSERT OR REPLACE INTO users (user_id,username,first_name,last_name,join_date,last_activity) VALUES (?,?,?,?,?,?)",
                  (uid, uname, fname, lname, now, now))
        c.commit(); c.close()

    def get_user(self, uid):
        c = self.conn()
        r = c.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        c.close(); return dict(r) if r else None

    def update_activity(self, uid):
        c = self.conn()
        c.execute("UPDATE users SET last_activity=?, calculation_count=calculation_count+1 WHERE user_id=?",
                  (datetime.now().isoformat(), uid))
        c.commit(); c.close()

    def get_all_users(self):
        c = self.conn()
        rows = [dict(r) for r in c.execute("SELECT * FROM users").fetchall()]
        c.close(); return rows

    # ── Materials ──
    def get_material(self, name):
        c = self.conn()
        r = c.execute("SELECT * FROM materials WHERE name=?", (name,)).fetchone()
        c.close(); return dict(r) if r else None

    def get_all_materials(self):
        c = self.conn()
        rows = [dict(r) for r in c.execute("SELECT * FROM materials ORDER BY category").fetchall()]
        c.close(); return rows

    def get_materials_by_category(self, cat):
        c = self.conn()
        rows = [dict(r) for r in c.execute("SELECT * FROM materials WHERE category=?", (cat,)).fetchall()]
        c.close(); return rows

    def update_material_price(self, name, price):
        c = self.conn()
        c.execute("UPDATE materials SET price=?, updated_at=? WHERE name=?", (price, datetime.now().isoformat(), name))
        c.commit(); c.close()

    def add_material(self, name, persian_name, unit, price, category):
        c = self.conn()
        c.execute("INSERT OR REPLACE INTO materials (name,persian_name,unit,price,category,updated_at) VALUES (?,?,?,?,?,?)",
                  (name, persian_name, unit, price, category, datetime.now().isoformat()))
        c.commit(); c.close()

    def delete_material(self, name):
        c = self.conn()
        c.execute("DELETE FROM materials WHERE name=?", (name,))
        c.commit(); c.close()

    # ── Settings ──
    def get_setting(self, key, default=""):
        c = self.conn()
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        c.close(); return r["value"] if r else default

    def set_setting(self, key, value):
        c = self.conn()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        c.commit(); c.close()

    # ── Estimation Prices ──
    def get_est_price(self, structure, quality):
        c = self.conn()
        r = c.execute("SELECT price FROM est_prices WHERE structure=? AND quality=?", (structure, quality)).fetchone()
        c.close(); return r["price"] if r else 20000000

    def set_est_price(self, structure, quality, price):
        c = self.conn()
        c.execute("INSERT OR REPLACE INTO est_prices (structure,quality,price) VALUES (?,?,?)", (structure, quality, price))
        c.commit(); c.close()

    def get_all_est_prices(self):
        c = self.conn()
        rows = [dict(r) for r in c.execute("SELECT * FROM est_prices ORDER BY structure, quality").fetchall()]
        c.close(); return rows

    # ── Calculations ──
    def save_calculation(self, uid, ctype, inp, res):
        c = self.conn()
        c.execute("INSERT INTO calculations (user_id,calc_type,input_data,result,created_at) VALUES (?,?,?,?,?)",
                  (uid, ctype, json.dumps(inp, ensure_ascii=False), json.dumps(res, ensure_ascii=False), datetime.now().isoformat()))
        c.commit(); c.close()

    def get_user_calculations(self, uid, limit=10):
        c = self.conn()
        rows = [dict(r) for r in c.execute("SELECT * FROM calculations WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (uid, limit)).fetchall()]
        c.close(); return rows

    # ── Stats ──
    def get_stats(self):
        c = self.conn()
        u = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        calc = c.execute("SELECT COUNT(*) FROM calculations").fetchone()[0]
        a = c.execute("SELECT COUNT(*) FROM users WHERE last_activity > datetime('now','-1 day')").fetchone()[0]
        m = c.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
        c.close()
        return {"total_users": u, "total_calculations": calc, "active_today": a, "total_materials": m}
