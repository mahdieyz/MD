from flask import Flask, render_template_string, request, redirect, url_for, session, flash, send_file
import os
import functools
import database

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "super-secret-key-tavansazeh-2025")
PANEL_USER = os.getenv("PANEL_USERNAME", "admin")
PANEL_PASS = os.getenv("PANEL_PASSWORD", "admin123")

def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def render_page(title, body_content):
    html = f"""
    <!DOCTYPE html>
    <html lang="fa" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title} - پنل مدیریت توان سازه</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>body {{ font-family: Tahoma, Arial, sans-serif; background: #f4f6f9; }}</style>
    </head>
    <body>
        <nav class="navbar navbar-expand-lg navbar-dark bg-dark mb-4">
            <div class="container">
                <a class="navbar-brand fw-bold" href="/">⚙️ پنل مدیریت توان سازه</a>
                <div class="navbar-nav me-auto">
                    <a class="nav-link text-white me-3" href="/">📊 داشبورد</a>
                    <a class="nav-link text-white me-3" href="/users">👥 کاربران</a>
                    <a class="nav-link text-white me-3" href="/buttons">🗂️ منوها</a>
                    <a class="nav-link text-white me-3" href="/settings">⚙️ تنظیمات و ریست</a>
                </div>
                <a href="/logout" class="btn btn-outline-danger btn-sm">خروج</a>
            </div>
        </nav>
        <div class="container">
            {{% with messages = get_flashed_messages(with_categories=true) %}}
              {{% if messages %}}
                {{% for category, message in messages %}}
                  <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
                    {{ message }}
                  </div>
                {{% endfor %}}
              {{% endif %}}
            {{% endwith %}}
            {body_content}
        </div>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/health')
def health_check():
    return "OK", 200

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('username') == PANEL_USER and request.form.get('password') == PANEL_PASS:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        flash('نام کاربری یا رمز عبور اشتباه است.', 'danger')
    
    login_html = """
    <!DOCTYPE html><html lang="fa" dir="rtl"><head><meta charset="UTF-8"><title>ورود به پنل</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head><body class="bg-light d-flex align-items-center justify-content-center" style="height: 100vh;">
    <div class="card shadow p-4" style="width: 360px;">
        <h4 class="text-center mb-4 font-weight-bold">ورود مدیریت</h4>
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}{% for cat, msg in messages %}
            <div class="alert alert-{{ cat }} py-2">{{ msg }}</div>
          {% endfor %}{% endif %}
        {% endwith %}
        <form method="POST">
            <input type="text" name="username" class="form-control mb-3" placeholder="نام کاربری" required>
            <input type="password" name="password" class="form-control mb-3" placeholder="رمز عبور" required>
            <button class="btn btn-primary w-100" type="submit">ورود به سیستم</button>
        </form>
    </div></body></html>
    """
    return render_template_string(login_html)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    user_count = database.get_user_count()
    buttons = database.get_buttons(0, admin_mode=True)
    body = f"""
    <h2 class="mb-4">داشبورد مدیریت</h2>
    <div class="row">
        <div class="col-md-4">
            <div class="card text-white bg-primary mb-3">
                <div class="card-body">
                    <h5 class="card-title">تعداد کاربران ربات</h5>
                    <p class="card-text fs-2">{user_count}</p>
                </div>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card text-white bg-success mb-3">
                <div class="card-body">
                    <h5 class="card-title">تعداد منوهای اصلی</h5>
                    <p class="card-text fs-2">{len(buttons)}</p>
                </div>
            </div>
        </div>
    </div>
    <div class="mt-4">
        <a href="/backup" class="btn btn-dark">📥 دانلود بک‌آپ دیتابیس (DB)</a>
    </div>
    """
    return render_page("داشبورد", body)

@app.route('/users')
@login_required
def users_page():
    users = database.get_all_users()
    rows = ""
    for u in users:
        status = "<span class='badge bg-danger'>مسدود</span>" if u['is_blocked'] else "<span class='badge bg-success'>فعال</span>"
        rows += f"""
        <tr>
            <td>{u['user_id']}</td>
            <td>@{u['username']}</td>
            <td>{u['full_name']}</td>
            <td>{u['joined_at']}</td>
            <td>{status}</td>
            <td>
                <a href="/toggle_block/{u['user_id']}" class="btn btn-sm btn-outline-warning">تغییر وضعیت مسدودی</a>
            </td>
        </tr>
        """
    body = f"""
    <h2>مدیریت کاربران</h2>
    <table class="table table-bordered table-striped mt-3">
        <thead class="table-dark">
            <tr><th>آیدی تلگرام</th><th>یوزرنیم</th><th>نام کامل</th><th>تاریخ عضویت</th><th>وضعیت</th><th>عملیات</th></tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """
    return render_page("کاربران", body)

@app.route('/toggle_block/<int:user_id>')
@login_required
def toggle_block(user_id):
    database.toggle_block_user(user_id)
    flash("وضعیت کاربر تغییر یافت.", "info")
    return redirect(url_for('users_page'))

@app.route('/buttons')
@login_required
def buttons_page():
    buttons = database.get_buttons(0, admin_mode=True)
    rows = ""
    for b in buttons:
        hidden = " (مخفی)" if b['is_hidden'] else ""
        rows += f"<li class='list-group-item d-flex justify-content-between align-items-center'>{b['title']}{hidden}</li>"
    
    body = f"""
    <h2>دکمه‌های ریشه منو</h2>
    <ul class="list-group mt-3 mb-4">{rows}</ul>
    <div class="alert alert-info">
        💡 برای افزودن، تغییر نام یا آپلود کاتالوگ در منوهای تودرتو، از دستور <code>/admin</code> در ربات تلگرام استفاده کنید.
    </div>
    """
    return render_page("منوها", body)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        database.update_setting('welcome_text', request.form.get('welcome_text'))
        database.update_setting('contact_text', request.form.get('contact_text'))
        flash("تنظیمات متنی با موفقیت ذخیره شد.", "success")
        return redirect(url_for('settings'))
    
    welcome = database.get_setting('welcome_text')
    contact = database.get_setting('contact_text')
    
    body = f"""
    <h2>تنظیمات ربات</h2>
    <form method="POST" class="mt-3">
        <div class="mb-3">
            <label class="form-label font-weight-bold">متن خوش‌آمدگویی (/start):</label>
            <textarea name="welcome_text" class="form-control" rows="3">{welcome}</textarea>
        </div>
        <div class="mb-3">
            <label class="form-label font-weight-bold">متن تماس با ما:</label>
            <textarea name="contact_text" class="form-control" rows="3">{contact}</textarea>
        </div>
        <button type="submit" class="btn btn-primary">ذخیره متون</button>
    </form>

    <hr class="my-5">

    <div class="card border-danger">
        <div class="card-header bg-danger text-white font-weight-bold">
            ⚠️ بازنشانی سیستم (Factory Reset)
        </div>
        <div class="card-body">
            <p class="card-text text-muted">
                با کلیک روی دکمه زیر، تمامی <strong>دکمه‌های منو</strong>، <strong>کاتالوگ‌ها/تصاویر</strong> و <strong>تنظیمات متن</strong> پاک شده و به حالت اول بازمی‌گردند. (لیست کاربران پاک نخواهد شد).
            </p>
            <form action="/reset_config" method="POST" onsubmit="return confirm('⚠️ آیا از بازنشانی کامل دکمه‌ها، کاتالوگ‌ها و تنظیمات اطمینان دارید؟ این عملیات غیرقابل بازگشت است!');">
                <button type="submit" class="btn btn-danger font-weight-bold">
                    🗑️ بازنشانی کامل دکمه‌ها، کاتالوگ‌ها و تنظیمات
                </button>
            </form>
        </div>
    </div>
    """
    return render_page("تنظیمات", body)

@app.route('/reset_config', methods=['POST'])
@login_required
def reset_config_route():
    if database.reset_bot_config():
        flash("تمامی دکمه‌ها، کاتالوگ‌ها و تنظیمات با موفقیت به حالت اولیه کارخانه بازگشتند.", "success")
    else:
        flash("خطا در بازنشانی اطلاعات.", "danger")
    return redirect(url_for('settings'))

@app.route('/backup')
@login_required
def backup():
    return send_file(database.DB_PATH, as_attachment=True)
