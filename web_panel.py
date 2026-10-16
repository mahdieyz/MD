import os
import time
import secrets
import functools
import requests
from flask import Flask, render_template_string, request, redirect, url_for, flash, session, send_file, abort
from database import Database

db = Database()

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', secrets.token_hex(32))

PANEL_USERNAME = os.environ.get('PANEL_USERNAME', 'admin')
PANEL_PASSWORD = os.environ.get('PANEL_PASSWORD', 'admin123')
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')

# Category mapping
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


def render_page(title, content_html, active_tab='dashboard'):
    full_html = f"""
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | پنل مدیریت توان‌سازه</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Segoe UI', Tahoma, system-ui, -apple-system, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            min-height: 100vh;
        }}
        .navbar {{
            background: #1e293b;
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3);
            position: sticky;
            top: 0;
            z-index: 100;
            border-bottom: 1px solid #334155;
        }}
        .navbar h1 {{ font-size: 1.25rem; color: #38bdf8; font-weight: 700; }}
        .navbar .nav-links {{ display: flex; gap: 0.5rem; flex-wrap: wrap; }}
        .navbar a {{
            color: #94a3b8;
            text-decoration: none;
            padding: 0.5rem 1rem;
            border-radius: 6px;
            font-size: 0.9rem;
            font-weight: 500;
            transition: all 0.2s;
        }}
        .navbar a:hover, .navbar a.active {{ color: #38bdf8; background: #334155; }}
        .navbar a.logout {{ color: #f87171; }}
        .navbar a.logout:hover {{ background: #450a0a; }}
        .container {{ max-width: 1200px; margin: 2rem auto; padding: 0 1.5rem; }}
        .card {{
            background: #1e293b;
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            border: 1px solid #334155;
            box-shadow: 0 10px 15px -3px rgba(0,0,0,0.2);
        }}
        .card h2 {{ color: #38bdf8; margin-bottom: 1.2rem; font-size: 1.15rem; font-weight: 600; }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1rem;
            margin-bottom: 1.5rem;
        }}
        .stat-card {{
            background: linear-gradient(135deg, #1e3a5f, #1e293b);
            border-radius: 10px;
            padding: 1.5rem;
            text-align: center;
            border: 1px solid #2d4a6f;
        }}
        .stat-card .number {{ font-size: 2.2rem; font-weight: 700; color: #38bdf8; }}
        .stat-card .label {{ color: #94a3b8; margin-top: 0.4rem; font-size: 0.88rem; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 0.5rem; font-size: 0.9rem; }}
        th, td {{ padding: 0.8rem 1rem; text-align: right; border-bottom: 1px solid #334155; }}
        th {{ background: #334155; color: #38bdf8; font-weight: 600; }}
        tr:hover {{ background: #253347; }}
        .btn {{
            display: inline-block;
            padding: 0.6rem 1.2rem;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            font-size: 0.88rem;
            font-weight: 600;
            text-decoration: none;
            transition: all 0.2s;
            font-family: inherit;
        }}
        .btn-primary {{ background: #0284c7; color: white; }}
        .btn-primary:hover {{ background: #0369a1; }}
        .btn-danger {{ background: #dc2626; color: white; }}
        .btn-danger:hover {{ background: #b91c1c; }}
        .btn-success {{ background: #16a34a; color: white; }}
        .btn-success:hover {{ background: #15803d; }}
        .btn-warning {{ background: #d97706; color: white; }}
        .btn-warning:hover {{ background: #b45309; }}
        .btn-sm {{ padding: 0.35rem 0.75rem; font-size: 0.8rem; }}
        input[type="text"], input[type="password"], textarea, select {{
            width: 100%;
            padding: 0.75rem 1rem;
            border-radius: 8px;
            border: 1px solid #475569;
            background: #0f172a;
            color: #e2e8f0;
            font-size: 0.9rem;
            font-family: inherit;
            margin-bottom: 0.8rem;
        }}
        textarea {{ min-height: 100px; resize: vertical; }}
        input:focus, textarea:focus, select:focus {{
            outline: none;
            border-color: #38bdf8;
            box-shadow: 0 0 0 3px rgba(56,189,248,0.2);
        }}
        .form-group {{ margin-bottom: 1.2rem; }}
        .form-group label {{ display: block; margin-bottom: 0.4rem; color: #94a3b8; font-size: 0.88rem; font-weight: 500; }}
        .alert {{
            padding: 0.8rem 1.2rem;
            border-radius: 8px;
            margin-bottom: 1.2rem;
            font-size: 0.9rem;
        }}
        .alert-success {{ background: #064e3b; border: 1px solid #10b981; color: #6ee7b7; }}
        .alert-danger {{ background: #450a0a; border: 1px solid #dc2626; color: #fca5a5; }}
        .badge {{
            display: inline-block;
            padding: 0.2rem 0.6rem;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
        }}
        .badge-green {{ background: #064e3b; color: #6ee7b7; }}
        .badge-red {{ background: #450a0a; color: #fca5a5; }}
        .badge-blue {{ background: #0c4a6e; color: #7dd3fc; }}
        .tabs {{ display: flex; gap: 0.5rem; margin-bottom: 1.2rem; flex-wrap: wrap; }}
        .tab {{
            padding: 0.45rem 0.9rem;
            border-radius: 8px;
            background: #334155;
            color: #94a3b8;
            text-decoration: none;
            font-size: 0.82rem;
            transition: all 0.2s;
        }}
        .tab:hover, .tab.active {{ background: #0284c7; color: white; }}
        .empty-state {{ text-align: center; padding: 2.5rem; color: #64748b; }}
        .empty-state .icon {{ font-size: 2.5rem; margin-bottom: 0.5rem; }}
        @media (max-width: 768px) {{
            .navbar {{ flex-direction: column; gap: 0.8rem; text-align: center; }}
            .navbar .nav-links {{ justify-content: center; }}
            .container {{ padding: 0 0.8rem; }}
        }}
    </style>
</head>
<body>
    <nav class="navbar">
        <h1>🔧 پنل مدیریت توان‌سازه</h1>
        <div class="nav-links">
            <a href="{url_for('dashboard')}" class="{'active' if active_tab=='dashboard' else ''}">📊 داشبورد</a>
            <a href="{url_for('users_page')}" class="{'active' if active_tab=='users' else ''}">👥 کاربران</a>
            <a href="{url_for('catalogs_page')}" class="{'active' if active_tab=='catalogs' else ''}">📁 کاتالوگ‌ها</a>
            <a href="{url_for('settings_page')}" class="{'active' if active_tab=='settings' else ''}">⚙️ تنظیمات</a>
            <a href="{url_for('broadcasts_page')}" class="{'active' if active_tab=='broadcasts' else ''}">📢 پیام‌ها</a>
            <a href="{url_for('backup_page')}" class="{'active' if active_tab=='backup' else ''}">💾 بکاپ</a>
            <a href="{url_for('logout')}" class="logout">🚪 خروج</a>
        </div>
    </nav>
    <div class="container">
        {{% with messages = get_flashed_messages(with_categories=true) %}}
        {{% if messages %}}
            {{% for category, message in messages %}}
            <div class="alert alert-{{{{ category }}}}">{{{{ message }}}}</div>
            {{% endfor %}}
        {{% endif %}}
        {{% endwith %}}
        {content_html}
    </div>
</body>
</html>
"""
    return render_template_string(full_html)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if username == PANEL_USERNAME and password == PANEL_PASSWORD:
            session['logged_in'] = True
            session['username'] = username
            flash('ورود با موفقیت انجام شد.', 'success')
            return redirect(url_for('dashboard'))
        flash('نام کاربری یا رمز عبور نادرست است.', 'danger')

    html = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ورود به پنل مدیریت</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', Tahoma, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .login-box { background: #1e293b; padding: 2.5rem; border-radius: 16px; width: 100%; max-width: 400px; border: 1px solid #334155; box-shadow: 0 10px 25px rgba(0,0,0,0.4); }
        .login-box h2 { text-align: center; color: #38bdf8; margin-bottom: 2rem; font-size: 1.4rem; }
        .form-group { margin-bottom: 1.2rem; }
        .form-group label { display: block; margin-bottom: 0.4rem; color: #94a3b8; font-size: 0.9rem; }
        input[type="text"], input[type="password"] { width: 100%; padding: 0.75rem 1rem; border-radius: 8px; border: 1px solid #475569; background: #0f172a; color: #e2e8f0; font-size: 0.95rem; }
        input:focus { outline: none; border-color: #38bdf8; }
        .btn { width: 100%; padding: 0.8rem; background: #0284c7; color: white; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 1rem; }
        .btn:hover { background: #0369a1; }
        .alert { padding: 0.8rem; border-radius: 8px; background: #450a0a; border: 1px solid #dc2626; color: #fca5a5; margin-bottom: 1rem; font-size: 0.9rem; text-align: center; }
    </style>
</head>
<body>
    <div class="login-box">
        <h2>🔐 ورود به پنل مدیریت</h2>
        {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
            {% for category, message in messages %}
            <div class="alert">{{ message }}</div>
            {% endfor %}
        {% endif %}
        {% endwith %}
        <form method="POST">
            <div class="form-group">
                <label>نام کاربری</label>
                <input type="text" name="username" required autofocus>
            </div>
            <div class="form-group">
                <label>رمز عبور</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit" class="btn">ورود</button>
        </form>
    </div>
</body>
</html>
"""
    return render_template_string(html)


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
        broadcast_rows += f"<tr><td>{b['sent_at'][:16]}</td><td>{(b['message_text'] or '')[:50]}...</td><td><span class='badge badge-green'>✅ {b['sent_count']}</span> <span class='badge badge-red'>❌ {b['fail_count']}</span></td></tr>"

    user_rows = ""
    for u in recent_users:
        status = "<span class='badge badge-green'>فعال</span>" if not u['is_blocked'] else "<span class='badge badge-red'>بلاک</span>"
        user_rows += f"<tr><td>{u['user_id']}</td><td>{u['first_name'] or '-'}</td><td>@{u['username'] or '-'}</td><td>{status}</td><td>{u['last_active'][:16] if u['last_active'] else '-'}</td></tr>"

    content = f"""
    <div class="stats-grid">
        <div class="stat-card"><div class="number">{total_users}</div><div class="label">👥 کل کاربران</div></div>
        <div class="stat-card"><div class="number">{active_users}</div><div class="label">✅ کاربران فعال</div></div>
        <div class="stat-card"><div class="number">{total_users - active_users}</div><div class="label">🚫 کاربران بلاک‌شده</div></div>
        <div class="stat-card"><div class="number">{total_files}</div><div class="label">📁 فایل‌ها</div></div>
    </div>

    <div class="card">
        <h2>📂 فایل‌ها به تفکیک دسته‌بندی</h2>
        {"<table><tr><th>دسته‌بندی</th><th>تعداد فایل</th></tr>" + cat_rows + "</table>" if cat_rows else "<div class='empty-state'><div class='icon'>📂</div>هنوز فایلی آپلود نشده است</div>"}
    </div>

    <div class="card">
        <h2>👥 آخرین کاربران عضو شده</h2>
        {"<table><tr><th>آیدی</th><th>نام</th><th>یوزرنیم</th><th>وضعیت</th><th>آخرین فعالیت</th></tr>" + user_rows + "</table>" if user_rows else "<div class='empty-state'><div class='icon'>👥</div>هنوز کاربری ثبت نشده است</div>"}
    </div>

    <div class="card">
        <h2>📢 آخرین پیام‌های همگانی</h2>
        {"<table><tr><th>تاریخ</th><th>متن پیام</th><th>نتیجه</th></tr>" + broadcast_rows + "</table>" if broadcast_rows else "<div class='empty-state'><div class='icon'>📢</div>هنوز پیامی ارسال نشده است</div>"}
    </div>
    """
    return render_page("داشبورد", content, 'dashboard')


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

    content = f"""
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
    """
    return render_page("مدیریت کاربران", content, 'users')


@app.route('/users/block/<int:user_id>')
@login_required
def block_user(user_id):
    db.block_user(user_id)
    flash(f'کاربر {user_id} مسدود شد.', 'success')
    return redirect(url_for('users_page'))


@app.route('/users/unblock/<int:user_id>')
@login_required
def unblock_user(user_id):
    db.unblock_user(user_id)
    flash(f'کاربر {user_id} از مسدودی خارج شد.', 'success')
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
                <a href="/catalogs/delete/{c['id']}" class="btn btn-danger btn-sm" onclick="return confirm('آیا از حذف این فایل مطمئن هستید؟')">🗑️</a>
            </td>
        </tr>"""

    cat_options = "".join([f'<option value="{c}">{c}</option>' for c in ALL_CATEGORIES])

    content = f"""
    <div class="card">
        <h2>📤 آپلود فایل جدید از مرورگر</h2>
        <form method="POST" action="/catalogs/upload" enctype="multipart/form-data">
            <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(200px, 1fr));gap:1rem;">
                <div class="form-group">
                    <label>دسته‌بندی</label>
                    <select name="category" required>{cat_options}</select>
                </div>
                <div class="form-group">
                    <label>انتخاب فایل (PDF یا عکس)</label>
                    <input type="file" name="file" required style="padding:0.45rem;">
                </div>
                <div class="form-group">
                    <label>یادداشت قیمت (اختیاری)</label>
                    <input type="text" name="custom_note" placeholder="مثلاً: لیست بعلاوه ۲۰ درصد میباشد">
                </div>
            </div>
            <button type="submit" class="btn btn-success">📤 آپلود و انتشار در ربات</button>
        </form>
    </div>

    <div class="card">
        <h2>📁 کاتالوگ‌های موجود ({len(catalogs)} فایل)</h2>
        <div class="tabs">{tabs}</div>
        <div style="overflow-x:auto;">
        <table>
            <tr><th>#</th><th>دسته‌بندی</th><th>نام فایل</th><th>نوع</th><th>یادداشت قیمت</th><th>تاریخ آپلود</th><th>عملیات</th></tr>
            {rows if rows else "<tr><td colspan='7'><div class='empty-state'><div class='icon'>📁</div>فایلی یافت نشد</div></td></tr>"}
        </table>
        </div>
    </div>
    """
    return render_page("مدیریت کاتالوگ‌ها", content, 'catalogs')


@app.route('/catalogs/upload', methods=['POST'])
@login_required
def upload_catalog_web():
    category = request.form.get('category')
    custom_note = request.form.get('custom_note', '').strip() or None
    file = request.files.get('file')

    if not file or not file.filename:
        flash('لطفاً فایلی انتخاب کنید.', 'danger')
        return redirect(url_for('catalogs_page'))

    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()

    if not BOT_TOKEN:
        flash('توکن ربات (BOT_TOKEN) تنظیم نشده است.', 'danger')
        return redirect(url_for('catalogs_page'))

    try:
        admin_id = os.environ.get('ADMIN_IDS', '').split(',')[0]
        if ext in ['.png', '.jpg', '.jpeg', '.webp']:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            files = {'photo': (filename, file.stream, file.mimetype)}
            data = {'chat_id': admin_id}
            resp = requests.post(url, files=files, data=data, timeout=30).json()

            if resp.get('ok'):
                file_id = resp['result']['photo'][-1]['file_id']
                file_type = 'photo'
            else:
                raise Exception(resp.get('description', 'Telegram API Upload Failed'))
        else:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
            files = {'document': (filename, file.stream, file.mimetype or 'application/pdf')}
            data = {'chat_id': admin_id}
            resp = requests.post(url, files=files, data=data, timeout=30).json()

            if resp.get('ok'):
                file_id = resp['result']['document']['file_id']
                file_type = 'document'
            else:
                raise Exception(resp.get('description', 'Telegram API Upload Failed'))

        catalog_id = db.add_catalog(
            category=category,
            file_id=file_id,
            file_type=file_type,
            caption=None,
            custom_note=custom_note,
            uploaded_by=None,
            original_filename=filename
        )

        flash(f'✅ فایل «{filename}» با موفقیت در دسته «{category}» ذخیره شد.', 'success')
    except Exception as e:
        flash(f'⚠️ خطا در آپلود فایل: {e}', 'danger')

    return redirect(url_for('catalogs_page'))


@app.route('/catalogs/edit/<int:catalog_id>', methods=['GET', 'POST'])
@login_required
def edit_catalog(catalog_id):
    cat = db.get_catalog_by_id(catalog_id)
    if not cat:
        flash('فایل مورد نظر یافت نشد.', 'danger')
        return redirect(url_for('catalogs_page'))

    if request.method == 'POST':
        new_note = request.form.get('custom_note', '').strip()
        db.update_catalog_note(catalog_id, new_note if new_note else None)
        flash(f'یادداشت فایل #{catalog_id} بروزرسانی شد.', 'success')
        return redirect(url_for('catalogs_page'))

    content = f"""
    <div class="card">
        <h2>✏️ ویرایش یادداشت فایل #{cat['id']}</h2>
        <p style="color:#94a3b8;margin-bottom:1rem;">دسته‌بندی: {cat['category']} | فایل: {cat['original_filename'] or '-'}</p>
        <form method="POST">
            <div class="form-group">
                <label>یادداشت قیمت</label>
                <input type="text" name="custom_note" value="{cat['custom_note'] or ''}" placeholder="مثلاً: لیست بعلاوه ۲۰ درصد میباشد">
            </div>
            <button type="submit" class="btn btn-success">💾 ذخیره تغییرات</button>
            <a href="/catalogs" class="btn btn-primary">بازگشت</a>
        </form>
    </div>
    """
    return render_page("ویرایش کاتالوگ", content, 'catalogs')


@app.route('/catalogs/delete/<int:catalog_id>')
@login_required
def delete_catalog(catalog_id):
    cat = db.get_catalog_by_id(catalog_id)
    if cat:
        db.delete_catalog(catalog_id)
        flash(f'فایل #{catalog_id} با موفقیت حذف شد.', 'success')
    else:
        flash('فایل یافت نشد.', 'danger')
    return redirect(url_for('catalogs_page'))


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings_page():
    if request.method == 'POST':
        form_type = request.form.get('form_type')
        if form_type == 'contact':
            contact = request.form.get('contact_text', '')
            db.set_setting('contact_text', contact)
            flash('اطلاعات تماس با موفقیت بروزرسانی شد.', 'success')
        elif form_type == 'welcome':
            welcome = request.form.get('welcome_text', '')
            db.set_setting('welcome_text', welcome)
            flash('پیام خوش‌آمدگویی با موفقیت بروزرسانی شد.', 'success')
        elif form_type == 'custom_setting':
            key = request.form.get('setting_key', '').strip()
            value = request.form.get('setting_value', '').strip()
            if key:
                db.set_setting(key, value)
                flash(f'تنظیم «{key}» ذخیره شد.', 'success')
        return redirect(url_for('settings_page'))

    contact = db.get_setting('contact_text', '')
    welcome = db.get_setting('welcome_text', '')
    all_settings = db.get_all_settings()

    settings_rows = ""
    for s in all_settings:
        settings_rows += f"<tr><td>{s['key']}</td><td>{s['value'][:100] if s['value'] else '-'}</td></tr>"

    content = f"""
    <div class="card">
        <h2>📞 اطلاعات تماس و ثبت سفارش</h2>
        <form method="POST">
            <input type="hidden" name="form_type" value="contact">
            <div class="form-group">
                <label>متن اطلاعات تماس (نمایش پس از کلیک کاربر روی دکمه "ثبت سفارش / تماس با ما")</label>
                <textarea name="contact_text" rows="5">{contact}</textarea>
            </div>
            <button type="submit" class="btn btn-success">💾 ذخیره تغییرات</button>
        </form>
    </div>

    <div class="card">
        <h2>👋 پیام خوش‌آمدگویی (/start)</h2>
        <form method="POST">
            <input type="hidden" name="form_type" value="welcome">
            <div class="form-group">
                <label>متن پیام خوش‌آمدگویی</label>
                <textarea name="welcome_text" rows="3">{welcome}</textarea>
            </div>
            <button type="submit" class="btn btn-success">💾 ذخیره تغییرات</button>
        </form>
    </div>

    <div class="card">
        <h2>➕ تنظیمات سفارشی سیستم</h2>
        <form method="POST">
            <input type="hidden" name="form_type" value="custom_setting">
            <div style="display:flex;gap:0.5rem;flex-wrap:wrap;">
                <input type="text" name="setting_key" placeholder="نام کلید" style="flex:1;min-width:150px;margin-bottom:0;">
                <input type="text" name="setting_value" placeholder="مقدار کلید" style="flex:2;min-width:200px;margin-bottom:0;">
                <button type="submit" class="btn btn-primary">افزودن</button>
            </div>
        </form>
    </div>

    <div class="card">
        <h2>📋 جدول کلی تنظیمات</h2>
        <table>
            <tr><th>کلید</th><th>مقدار</th></tr>
            {settings_rows if settings_rows else "<tr><td colspan='2'><div class='empty-state'>تنظیمی ذخیره نشده است</div></td></tr>"}
        </table>
    </div>
    """
    return render_page("تنظیمات", content, 'settings')


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
            <td style="max-width:300px;word-break:break-word;">{(b['message_text'] or '')[:200]}</td>
            <td><span class="badge badge-green">✅ {b['sent_count']}</span></td>
            <td><span class="badge badge-red">❌ {b['fail_count']}</span></td>
            <td>{total}</td>
            <td>{b['sent_by'] or '-'}</td>
        </tr>"""

    content = f"""
    <div class="card">
        <h2>📢 تاریخچه پیام‌های همگانی</h2>
        <p style="color:#94a3b8;margin-bottom:1.2rem;">گزارش تمام پیام‌های همگانی ارسال شده از طریق ربات تلگرام (/admin)</p>
        <div style="overflow-x:auto;">
        <table>
            <tr><th>#</th><th>تاریخ ارسال</th><th>متن پیام</th><th>موفق</th><th>ناموفق</th><th>مجموع</th><th>ارسال‌کننده</th></tr>
            {rows if rows else "<tr><td colspan='7'><div class='empty-state'><div class='icon'>📢</div>هنوز پیامی ارسال نشده است</div></td></tr>"}
        </table>
        </div>
    </div>
    """
    return render_page("تاریخچه پیام‌ها", content, 'broadcasts')


@app.route('/backup')
@login_required
def backup_page():
    content = """
    <div class="card">
        <h2>💾 دانلود بکاپ دیتابیس</h2>
        <p style="color:#94a3b8;margin-bottom:1.5rem;">دانلود نسخه کامل دیتابیس به همراه تمام کاربران، کاتالوگ‌ها و تنظیمات.</p>
        <div>
            <a href="/backup/download" class="btn btn-success" style="padding:0.8rem 1.8rem;">💾 دانلود فایل .db</a>
        </div>
    </div>

    <div class="card">
        <h2>📥 بازگردانی بکاپ</h2>
        <p style="color:#fca5a5;margin-bottom:1rem;">⚠️ توجه: بازگردانی بکاپ تمام اطلاعات فعلی دیتابیس را جایگزین خواهد کرد. قبل از اقدام، بکاپ جدید تهیه کنید.</p>
        <form method="POST" action="/backup/restore" enctype="multipart/form-data">
            <div class="form-group">
                <label>فایل بکاپ (.db)</label>
                <input type="file" name="backup_file" accept=".db" style="padding:0.45rem;">
            </div>
            <button type="submit" class="btn btn-danger" onclick="return confirm('آیا مطمئن هستید؟ اطلاعات فعلی دیتابیس بازنویسی خواهد شد.')">📥 بازگردانی کامل</button>
        </form>
    </div>
    """
    return render_page("مدیریت بکاپ", content, 'backup')


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
        flash('فایلی انتخاب نشده است.', 'danger')
        return redirect(url_for('backup_page'))

    file = request.files['backup_file']
    if not file.filename.endswith('.db'):
        flash('فقط فایل‌های پسوند .db مجاز هستند.', 'danger')
        return redirect(url_for('backup_page'))

    try:
        tmp_path = f"/tmp/web_restore_{int(time.time())}.db"
        file.save(tmp_path)
        db.restore_from_file(tmp_path)
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        flash('✅ دیتابیس با موفقیت بازگردانی شد.', 'success')
    except Exception as e:
        flash(f'خطا در بازگردانی: {e}', 'danger')

    return redirect(url_for('backup_page'))


@app.route('/health')
def health():
    return {'status': 'ok', 'users': db.get_user_count(), 'catalogs': db.get_catalog_count()}, 200
