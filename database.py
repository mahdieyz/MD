import os
import json
import sqlite3
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
        """)
        c.commit()
        c.close()
        self._seed_materials()

    def _seed_materials(self):
        c = self.conn()
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
        now = datetime.now().isoformat()
        for m in mats:
            c.execute("INSERT OR IGNORE INTO materials (name,persian_name,unit,price,category,updated_at) VALUES (?,?,?,?,?,?)", (*m, now))
        c.commit()
        c.close()

    def add_user(self, uid, uname, fname, lname):
        c = self.conn()
        now = datetime.now().isoformat()
        c.execute("INSERT OR REPLACE INTO users (user_id,username,first_name,last_name,join_date,last_activity) VALUES (?,?,?,?,?,?)",
                  (uid, uname, fname, lname, now, now))
        c.commit(); c.close()

    def get_user(self, uid):
        c = self.conn()
        r = c.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        c.close()
        return dict(r) if r else None

    def update_activity(self, uid):
        c = self.conn()
        c.execute("UPDATE users SET last_activity=?, calculation_count=calculation_count+1 WHERE user_id=?",
                  (datetime.now().isoformat(), uid))
        c.commit(); c.close()

    def get_all_users(self):
        c = self.conn()
        rows = [dict(r) for r in c.execute("SELECT * FROM users").fetchall()]
        c.close(); return rows

    def get_material(self, name):
        c = self.conn()
        r = c.execute("SELECT * FROM materials WHERE name=?", (name,)).fetchone()
        c.close()
        return dict(r) if r else None

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

    def save_calculation(self, uid, ctype, inp, res):
        c = self.conn()
        c.execute("INSERT INTO calculations (user_id,calc_type,input_data,result,created_at) VALUES (?,?,?,?,?)",
                  (uid, ctype, json.dumps(inp, ensure_ascii=False), json.dumps(res, ensure_ascii=False), datetime.now().isoformat()))
        c.commit(); c.close()

    def get_user_calculations(self, uid, limit=10):
        c = self.conn()
        rows = [dict(r) for r in c.execute("SELECT * FROM calculations WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (uid, limit)).fetchall()]
        c.close(); return rows

    def get_stats(self):
        c = self.conn()
        u = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        calc = c.execute("SELECT COUNT(*) FROM calculations").fetchone()[0]
        a = c.execute("SELECT COUNT(*) FROM users WHERE last_activity > datetime('now','-1 day')").fetchone()[0]
        c.close()
        return {"total_users": u, "total_calculations": calc, "active_today": a}
