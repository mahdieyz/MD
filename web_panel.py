import os
import time
import secrets
import functools
from flask import Flask, render_template_string, request, redirect, url_for, flash, session, send_file, abort
from database import Database

db = Database()

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', secrets.token_hex(32))

PANEL_USERNAME = os.environ.get('PANEL_USERNAME', 'admin')
PANEL_PASSWORD = os.environ.get('PANEL_PASSWORD', 'admin123')

# ─── Menu structure (same as bot) ───
MAIN_CATEGORIES = [
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

SUB_CATEGORIES = {
    "نمای ساختمان - محوطه - استخری": ["مد نور", "شعاع", "انوار"],
    "کلید ، پریز هوشمند و مکانیکی": ["هوشمند", "مکانیکی"],
}

ALL_CATEGORIES = []
for cat in MAIN_CATEGORIES:
    if cat in SUB_CATEGORIES:
        ALL_CATEGORIES.extend(SUB_CATEGORIES[cat])
    else:
        ALL_CATEGORIES.append(cat)


def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ─── Embedded HTML Template (Complete) ───
BASE_HTML = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>پنل مدیریت ربات توان‌سازه</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Segoe UI', Tahoma, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            min-height: 100vh;
        }
        .navbar {
            background: linear-gradient(135deg, #1e293b, #334155);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.3);
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .navbar h1 { font-size: 1.3rem; color: #38bdf8; }
        .navbar a { color: #94a3b8; text-decoration: none; margin-right: 1.5rem; font-size: 0.95rem; transition: color 0.2s; }
        .navbar a:hover { color: #38bdf8; }
        .navbar .nav-links { display: flex; gap: 0.5rem; flex-wrap: wrap; }
        .container { max-width: 1200px; margin: 2rem auto; padding: 0 1.5rem; }
        .card {
            background: #1e293b;
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            border: 1px solid #334155;
            box-shadow: 0 4px 6px rgba(0,0,0,0.2);
        }
        .card h2 { color: #38bdf8; margin-bottom: 1rem; font-size: 1.2rem; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
        }
        .stat-card {
            background: linear-gradient(135deg, #1e3a5f, #1e293b);
            border-radius: 10px;
            padding: 1.5rem;
            text-align: center;
            border: 1px solid #2d4a6f;
        }
        .stat-card .number { font-size: 2.5rem; font-weight: bold; color: #38bdf8; }
        .stat-card .label { color: #94a3b8; margin-top: 0.5rem; font-size: 0.9rem; }
        table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
        th, td { padding: 0.75rem 1rem; text-align: right; border-bottom: 1px solid #334155; }
        th { background: #334155; color: #38bdf8; font-weight: 600; }
        tr:hover { background: #253347; }
        .btn {
            display: inline-block;
            padding: 0.5rem 1.2rem;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            font-size: 0.9rem;
            text-decoration: none;
            transition: all 0.2s;
            font-family: inherit;
        }
        .btn-primary { background: #2563eb; color: white; }
        .btn-primary:hover { background: #1d4ed8; }
        .btn-danger { background: #dc2626; color: white; }
        .btn-danger:hover { background: #b91c1c; }
        .btn-success { background: #16a34a; color: white; }
        .btn-success:hover { background: #15803d; }
        .btn-warning { background: #d97706; color: white; }
        .btn-warning:hover { background: #b45309; }
        .btn-sm { padding: 0.3rem 0.8rem; font-size: 0.8rem; }
        input[type="text"], input[type="password"], textarea, select {
            width: 100%;
            padding: 0.7rem 1rem;
            border-radius: 8px;
            border: 1px solid #475569;
            background: #0f172a;
            color: #e2e8f0;
            font-size: 0.95rem;
            font-family: inherit;
            margin-bottom: 0.8rem;
        }
        textarea { min-height: 100px; resize: vertical; }
        input:focus, textarea:focus, select:focus {
            outline: none;
            border-color: #38bdf8;
            box-shadow: 0 0 0 2px rgba(56,189,248,0.2);
        }
        .form-group { margin-bottom: 1rem; }
        .form-group label { display: block; margin-bottom: 0.4rem; color: #94a3b8; font-size: 0.9rem; }
        .alert {
            padding: 0.8rem 1.2rem;
            border-radius: 8px;
            margin-bottom: 1rem;
            font-size: 0.9rem;
        }
        .alert-success { background: #064e3b; border: 1px solid #10b981; color: #6ee7b7; }
        .alert-danger { background: #450a0a; border: 1px solid #dc2626; color: #fca5a5; }
        .alert-info { background: #0c4a6e; border: 1px solid #0284c7; color: #7dd3fc; }
        .login-container {
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }
        .login-box {
            background: #1e293b;
            padding: 2.5rem;
            border-radius: 16px;
            width: 100%;
            max-width: 400px;
            border: 1px solid #334155;
        }
        .login-box h2 { text-align: center; color: #38bdf8; margin-bottom: 2rem; }
        .badge {
            display: inline-block;
            padding: 0.2rem 0.6rem;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .badge-green { background: #064e3b; color: #6ee7b7; }
        .badge-red { background: #450a0a; color: #fca5a5; }
        .badge-blue { background: #0c4a6e; color: #7dd3fc; }
        .tabs { display: flex; gap: 0.5rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
        .tab {
            padding: 0.5rem 1rem;
            border-radius: 8px;
            background: #334155;
            color: #94a3b8;
            text-decoration: none;
            font-size: 0.85rem;
            transition: all 0.2s;
        }
        .tab:hover, .tab.active { background: #2563eb; color: white; }
        .empty-state {
            text-align: center;
            padding: 3rem;
            color: #64748b;
        }
        .empty-state .icon { font-size: 3rem; margin-bottom: 1rem; }
        @media (max-width: 768px) {
            .navbar { flex-direction: column; gap: 0.5rem; }
            .navbar .nav-links { justify-content: center; }
            .container { padding: 0 0.8rem; }
        }
    </style>
</head>
<body>
{% if session.get('logged_in') %}
<nav class="navbar">
    <h1>🔧 پنل مدیریت توان‌سازه</h1>
    <div class="nav-links">
        <a href="{{ url_for('dashboard') }}">📊 داشبورد</a>
        <a href="{{ url_for('users_page') }}">👥 کاربران</a>
        <a href="{{ url_for('catalogs_page') }}">📁 کاتالوگ‌ها</a>
        <a href="{{ url_for('settings_page') }}">⚙️ تنظیمات</a>
        <a href="{{ url_for('broadcasts_page') }}">📢 پیام‌ها</a>
        <a href="{{ url_for('backup_page') }}">💾 بکاپ</a>
        <a href="{{ url_for('logout') }}">🚪 خروج</a>
    </div>
</nav>
{% endif %}
<div class="container">
    {% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
        {% for category, message in messages %}
        <div class="alert alert-{{ category }}">{{ message }}</div>
        {% endfor %}
    {% endif %}
    {% endwith %}
    {% block content %}{% endblock %}
</div>
</body>
</html>
"""


# ──────── ROUTES ────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if username == PANEL_USERNAME and password == PANEL_PASSWORD:
            session['logged_in'] = True
            session['username'] = username
            flash('ورود موفق', 'success')
            return redirect(url_for('dashboard'))
        flash('نام کاربری یا رمز عبور اشتباه است', 'danger')

    html = """
    {% extends "base" %}
    {% block content %}
    <div class="login-container" style="margin-top:-2rem">
        <div class="login-box">
            <h2>🔐 ورود به پنل</h2>
            <form method="POST">
                <div class="form-group">
                    <label>نام کاربری</label>
                    <input type="text" name="username" required autofocus>
                </div>
                <div class="form-group">
                    <label>رمز عبور</label>
                    <input type="password" name="password" required>
                </div>
                <button type="submit" class="btn btn-primary" style="width:100%;padding:0.8rem;">ورود</button>
            </form>
        </div>
    </div>
    {% endblock %}
    """
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', '') +
        '<div class="login-container"><div class="login-box"><h2>🔐 ورود به پنل</h2>' +
        ('<div class="alert alert-danger">نام کاربری یا رمز عبور اشتباه است</div>' if request.method == 'POST' and not session.get('logged_in') else '') +
        '<form method="POST"><div class="form-group"><label>نام کاربری</label><input type="text" name="username" required autofocus></div><div class="form-group"><label>رمز عبور</label><input type="password" name="password" required></div><button type="submit" class="btn btn-primary" style="width:100%;padding:0.8rem;">ورود</button></form></div></div></div></body></html>')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def dashboard():
    total_users = db.get_user_count()
    active_users = db.get_active_user_count()
    total_files = db.get_catalog_count()
    cat_stats = db.get_category_stats()
    recent_broadcasts = db.get_broadcast_logs(5)
    recent_users = db.get_all_users()[:10]

    cat_rows = ""
    for cs in cat_stats:
        cat_rows += f"<tr><td>{cs['category']}</td><td>{cs['cnt']}</td></tr>"

    broadcast_rows = ""
    for b in recent_broadcasts:
        broadcast_rows += f"<tr><td>{b['sent_at'][:16]}</td><td>{b['message_text'][:50]}...</td><td><span class='badge badge-green'>✅ {b['sent_count']}</span> <span class='badge badge-red'>❌ {b['fail_count']}</span></td></tr>"

    user_rows = ""
    for u in recent_users:
        status = "<span class='badge badge-green'>فعال</span>" if not u['is_blocked'] else "<span class='badge badge-red'>بلاک</span>"
        user_rows += f"<tr><td>{u['user_id']}</td><td>{u['first_name'] or '-'}</td><td>@{u['username'] or '-'}</td><td>{status}</td><td>{u['last_active'][:16] if u['last_active'] else '-'}</td></tr>"

    html = BASE_HTML.replace('{% block content %}{% endblock %}', f"""
    <div class="stats-grid">
        <div class="stat-card"><div class="number">{total_users}</div><div class="label">👥 کل کاربران</div></div>
        <div class="stat-card"><div class="number">{active_users}</div><div class="label">✅ کاربران فعال</div></div>
        <div class="stat-card"><div class="number">{total_users - active_users}</div><div class="label">🚫 بلاک شده</div></div>
        <div class="stat-card"><div class="number">{total_files}</div><div class="label">📁 فایل‌ها</div></div>
    </div>

    <div class="card">
        <h2>📂 فایل‌ها به تفکیک دسته‌بندی</h2>
        {"<table><th>دسته‌بندی</th><th>تعداد</th>" + cat_rows + "</table>" if cat_rows else "<div class='empty-state'><div class='icon'>📂</div>هنوز فایلی آپلود نشده</div>"}
    </div>

    <div class="card">
        <h2>👥 آخرین کاربران</h2>
        {"<table><th>آیدی</th><th>نام</th><th>یوزرنیم</th><th>وضعیت</th><th>آخرین فعالیت</th>" + user_rows + "</table>" if user_rows else "<div class='empty-state'><div class='icon'>👥</div>هنوز کاربری ثبت نشده</div>"}
    </div>

    <div class="card">
        <h2>📢 آخرین پیام‌های همگانی</h2>
        {"<table><th>تاریخ</th><th>متن</th><th>نتیجه</th>" + broadcast_rows + "</table>" if broadcast_rows else "<div class='empty-state'><div class='icon'>📢</div>هنوز پیامی ارسال نشده</div>"}
    </div>
    """)
    return html


@app.route('/users')
@login_required
def users_page():
    users = db.get_all_users()
    search = request.args.get('q', '').strip()

    rows = ""
    for u in users:
        if search:
            match = (search.lower() in str(u['user_id']) or
                     search.lower() in (u['username'] or '').lower() or
                     search.lower() in (u['first_name'] or '').lower() or
                     search.lower() in (u['last_name'] or '').lower())
            if not match:
                continue

        status = "<span class='badge badge-green'>فعال</span>" if not u['is_blocked'] else "<span class='badge badge-red'>بلاک</span>"
        action = f"<a href='/users/block/{u['user_id']}' class='btn btn-danger btn-sm'>بلاک</a>" if not u['is_blocked'] else f"<a href='/users/unblock/{u['user_id']}' class='btn btn-success btn-sm'>آنبلاک</a>"
        rows += f"<tr><td>{u['user_id']}</td><td>{u['first_name'] or '-'}</td><td>{u['last_name'] or '-'}</td><td>@{u['username'] or '-'}</td><td>{status}</td><td>{u['joined_at'][:16] if u['joined_at'] else '-'}</td><td>{u['last_active'][:16] if u['last_active'] else '-'}</td><td>{action}</td></tr>"

    html = BASE_HTML.replace('{% block content %}{% endblock %}', f"""
    <div class="card">
        <h2>👥 مدیریت کاربران ({len(users)} نفر)</h2>
        <form method="GET" style="margin-bottom:1rem;display:flex;gap:0.5rem;">
            <input type="text" name="q" placeholder="جستجو بر اساس نام، یوزرنیم یا آیدی..." value="{search}" style="margin-bottom:0;">
            <button type="submit" class="btn btn-primary">جستجو</button>
        </form>
        <div style="overflow-x:auto;">
        <table>
            <tr><th>آیدی</th><th>نام</th><th>نام خانوادگی</th><th>یوزرنیم</th><th>وضعیت</th><th>تاریخ عضویت</th><th>آخرین فعالیت</th><th>عملیات</th></tr>
            {rows if rows else "<tr><td colspan='8'><div class='empty-state'><div class='icon'>👥</div>کاربری یافت نشد</div></td></tr>"}
        </table>
        </div>
    </div>
    """)
    return html


@app.route('/users/block/<int:user_id>')
@login_required
def block_user(user_id):
    db.block_user(user_id)
    flash(f'کاربر {user_id} بلاک شد', 'success')
    return redirect(url_for('users_page'))


@app.route('/users/unblock/<int:user_id>')
@login_required
def unblock_user(user_id):
    db.unblock_user(user_id)
    flash(f'کاربر {user_id} آنبلاک شد', 'success')
    return redirect(url_for('users_page'))


@app.route('/catalogs')
@login_required
def catalogs_page():
    selected_cat = request.args.get('category', '')
    catalogs = db.get_catalogs(selected_cat if selected_cat else None)

    tabs = '<a href="/catalogs" class="tab ' + ('active' if not selected_cat else '') + '">همه</a>'
    for cat in ALL_CATEGORIES:
        active = 'active' if selected_cat == cat else ''
        tabs += f'<a href="/catalogs?category={cat}" class="tab {active}">{cat}</a>'

    rows = ""
    for c in catalogs:
        fname = c['original_filename'] or '-'
        ftype = "<span class='badge badge-blue'>📄 سند</span>" if c['file_type'] == 'document' else "<span class='badge badge-green'>🖼️ عکس</span>"
        note = c['custom_note'] or '-'
        rows += f"""<tr>
            <td>{c['id']}</td>
            <td>{c['category']}</td>
            <td>{fname}</td>
            <td>{ftype}</td>
            <td>{note}</td>
            <td>{c['uploaded_at'][:16] if c['uploaded_at'] else '-'}</td>
            <td>
                <a href="/catalogs/edit/{c['id']}" class="btn btn-warning btn-sm">✏️</a>
                <a href="/catalogs/delete/{c['id']}" class="btn btn-danger btn-sm" onclick="return confirm('آیا مطمئن هستید؟')">🗑️</a>
            </td>
        </tr>"""

    html = BASE_HTML.replace('{% block content %}{% endblock %}', f"""
    <div class="card">
        <h2>📁 مدیریت کاتالوگ‌ها ({len(catalogs)} فایل)</h2>
        <div class="tabs">{tabs}</div>
        <div style="overflow-x:auto;">
        <table>
            <tr><th>#</th><th>دسته‌بندی</th><th>نام فایل</th><th>نوع</th><th>یادداشت قیمت</th><th>تاریخ آپلود</th><th>عملیات</th></tr>
            {rows if rows else "<tr><td colspan='7'><div class='empty-state'><div class='icon'>📁</div>فایلی یافت نشد</div></td></tr>"}
        </table>
        </div>
    </div>
    """)
    return html


@app.route('/catalogs/edit/<int:catalog_id>', methods=['GET', 'POST'])
@login_required
def edit_catalog(catalog_id):
    cat = db.get_catalog_by_id(catalog_id)
    if not cat:
        flash('فایل یافت نشد', 'danger')
        return redirect(url_for('catalogs_page'))

    if request.method == 'POST':
        new_note = request.form.get('custom_note', '').strip()
        db.update_catalog_note(catalog_id, new_note if new_note else None)
        flash(f'یادداشت فایل #{catalog_id} بروزرسانی شد', 'success')
        return redirect(url_for('catalogs_page'))

    html = BASE_HTML.replace('{% block content %}{% endblock %}', f"""
    <div class="card">
        <h2>✏️ ویرایش فایل #{cat['id']}</h2>
        <p style="color:#94a3b8;margin-bottom:1rem;">دسته: {cat['category']} | فایل: {cat['original_filename'] or '-'}</p>
        <form method="POST">
            <div class="form-group">
                <label>یادداشت قیمت</label>
                <input type="text" name="custom_note" value="{cat['custom_note'] or ''}" placeholder="مثلاً: لیست بعلاوه ۲۰ درصد میباشد">
            </div>
            <button type="submit" class="btn btn-success">💾 ذخیره</button>
            <a href="/catalogs" class="btn btn-primary">بازگشت</a>
        </form>
    </div>
    """)
    return html


@app.route('/catalogs/delete/<int:catalog_id>')
@login_required
def delete_catalog(catalog_id):
    cat = db.get_catalog_by_id(catalog_id)
    if cat:
        db.delete_catalog(catalog_id)
        flash(f'فایل #{catalog_id} حذف شد', 'success')
    else:
        flash('فایل یافت نشد', 'danger')
    return redirect(url_for('catalogs_page'))


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings_page():
    if request.method == 'POST':
        form_type = request.form.get('form_type')
        if form_type == 'contact':
            contact = request.form.get('contact_text', '')
            db.set_setting('contact_text', contact)
            flash('اطلاعات تماس بروزرسانی شد', 'success')
        elif form_type == 'welcome':
            welcome = request.form.get('welcome_text', '')
            db.set_setting('welcome_text', welcome)
            flash('پیام خوش‌آمدگویی بروزرسانی شد', 'success')
        elif form_type == 'custom_setting':
            key = request.form.get('setting_key', '').strip()
            value = request.form.get('setting_value', '').strip()
            if key:
                db.set_setting(key, value)
                flash(f'تنظیم "{key}" ذخیره شد', 'success')
        return redirect(url_for('settings_page'))

    contact = db.get_setting('contact_text', '')
    welcome = db.get_setting('welcome_text', '')
    all_settings = db.get_all_settings()

    settings_rows = ""
    for s in all_settings:
        settings_rows += f"<tr><td>{s['key']}</td><td>{s['value'][:100] if s['value'] else '-'}</td></tr>"

    html = BASE_HTML.replace('{% block content %}{% endblock %}', f"""
    <div class="card">
        <h2>📞 اطلاعات تماس و سفارش</h2>
        <form method="POST">
            <input type="hidden" name="form_type" value="contact">
            <div class="form-group">
                <label>متن اطلاعات تماس (نمایش به کاربر هنگام کلیک روی "ثبت سفارش / تماس با ما")</label>
                <textarea name="contact_text" rows="5">{contact}</textarea>
            </div>
            <button type="submit" class="btn btn-success">💾 ذخیره</button>
        </form>
    </div>

    <div class="card">
        <h2>👋 پیام خوش‌آمدگویی</h2>
        <form method="POST">
            <input type="hidden" name="form_type" value="welcome">
            <div class="form-group">
                <label>متن پیام خوش‌آمدگویی (ارسال به کاربر هنگام /start)</label>
                <textarea name="welcome_text" rows="3">{welcome}</textarea>
            </div>
            <button type="submit" class="btn btn-success">💾 ذخیره</button>
        </form>
    </div>

    <div class="card">
        <h2>➕ تنظیم دلخواه</h2>
        <form method="POST">
            <input type="hidden" name="form_type" value="custom_setting">
            <div style="display:flex;gap:0.5rem;flex-wrap:wrap;">
                <input type="text" name="setting_key" placeholder="کلید" style="flex:1;min-width:150px;">
                <input type="text" name="setting_value" placeholder="مقدار" style="flex:2;min-width:200px;">
                <button type="submit" class="btn btn-primary" style="margin-bottom:0.8rem;">افزودن</button>
            </div>
        </form>
    </div>

    <div class="card">
        <h2>📋 همه تنظیمات</h2>
        <table>
            <tr><th>کلید</th><th>مقدار</th></tr>
            {settings_rows if settings_rows else "<tr><td colspan='2'><div class='empty-state'>تنظیمی ذخیره نشده</div></td></tr>"}
        </table>
    </div>
    """)
    return html


@app.route('/broadcasts')
@login_required
def broadcasts_page():
    logs = db.get_broadcast_logs(100)
    rows = ""
    for b in logs:
        total = b['sent_count'] + b['fail_count']
        rows += f"""<tr>
            <td>{b['id']}</td>
            <td>{b['sent_at'][:19] if b['sent_at'] else '-'}</td>
            <td style="max-width:300px;word-break:break-word;">{b['message_text'][:200] if b['message_text'] else '-'}</td>
            <td><span class="badge badge-green">✅ {b['sent_count']}</span></td>
            <td><span class="badge badge-red">❌ {b['fail_count']}</span></td>
            <td>{total}</td>
            <td>{b['sent_by'] or '-'}</td>
        </tr>"""

    html = BASE_HTML.replace('{% block content %}{% endblock %}', f"""
    <div class="card">
        <h2>📢 تاریخچه پیام‌های همگانی</h2>
        <p style="color:#94a3b8;margin-bottom:1rem;">پیام‌های همگانی از طریق ربات تلگرام (دستور /admin) ارسال می‌شوند.</p>
        <div style="overflow-x:auto;">
        <table>
            <tr><th>#</th><th>تاریخ</th><th>متن</th><th>موفق</th><th>ناموفق</th><th>کل</th><th>ارسال‌کننده</th></tr>
            {rows if rows else "<tr><td colspan='7'><div class='empty-state'><div class='icon'>📢</div>هنوز پیامی ارسال نشده</div></td></tr>"}
        </table>
        </div>
    </div>
    """)
    return html


@app.route('/backup')
@login_required
def backup_page():
    html = BASE_HTML.replace('{% block content %}{% endblock %}', """
    <div class="card">
        <h2>💾 مدیریت بکاپ</h2>
        <p style="color:#94a3b8;margin-bottom:1.5rem;">دانلود بکاپ فعلی دیتابیس یا بازگردانی از فایل بکاپ قبلی</p>
        <div style="display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:2rem;">
            <a href="/backup/download" class="btn btn-success" style="padding:1rem 2rem;font-size:1rem;">💾 دانلود بکاپ دیتابیس</a>
        </div>
    </div>

    <div class="card">
        <h2>📥 بازگردانی بکاپ</h2>
        <p style="color:#fca5a5;margin-bottom:1rem;">⚠️ توجه: بازگردانی بکاپ، دیتابیس فعلی را جایگزین می‌کند. قبل از بازگردانی حتماً بکاپ بگیرید.</p>
        <form method="POST" action="/backup/restore" enctype="multipart/form-data">
            <div class="form-group">
                <label>فایل بکاپ (.db)</label>
                <input type="file" name="backup_file" accept=".db" style="padding:0.5rem;">
            </div>
            <button type="submit" class="btn btn-danger" onclick="return confirm('آیا مطمئن هستید؟ دیتابیس فعلی جایگزین خواهد شد.')">📥 بازگردانی</button>
        </form>
    </div>
    """)
    return html


@app.route('/backup/download')
@login_required
def download_backup():
    try:
        backup_path = f"/tmp/web_backup_{int(time.time())}.db"
        db.backup_to_file(backup_path)
        return send_file(backup_path, as_attachment=True, download_name=f"bot_backup_{int(time.time())}.db")
    except Exception as e:
        flash(f'خطا در ایجاد بکاپ: {e}', 'danger')
        return redirect(url_for('backup_page'))


@app.route('/backup/restore', methods=['POST'])
@login_required
def restore_backup():
    if 'backup_file' not in request.files:
        flash('فایلی انتخاب نشده', 'danger')
        return redirect(url_for('backup_page'))

    file = request.files['backup_file']
    if not file.filename.endswith('.db'):
        flash('فقط فایل‌های .db مجاز هستند', 'danger')
        return redirect(url_for('backup_page'))

    try:
        tmp_path = f"/tmp/web_restore_{int(time.time())}.db"
        file.save(tmp_path)
        db.restore_from_file(tmp_path)
        os.remove(tmp_path)
        flash('✅ دیتابیس با موفقیت بازگردانی شد', 'success')
    except Exception as e:
        flash(f'خطا در بازگردانی: {e}', 'danger')

    return redirect(url_for('backup_page'))


@app.route('/health')
def health():
    return {'status': 'ok', 'users': db.get_user_count(), 'catalogs': db.get_catalog_count()}, 200
