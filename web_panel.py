from flask import Flask, render_template_string, request, redirect, url_for, session, flash, send_file
import os
import functools
import database

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "super-secret-key-tavansazeh")
PANEL_USER = os.getenv("PANEL_USERNAME", "admin")
PANEL_PASS = os.getenv("PANEL_PASSWORD", "admin123")

def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>پنل مدیریت توان سازه</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>body { font-family: Tahoma, Arial; background: #f8f9fa; }</style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark mb-4">
        <div class="container">
            <a class="navbar-brand" href="/">پنل مدیریت ربات</a>
            <div class="collapse navbar-collapse">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item"><a class="nav-link" href="/users">کاربران</a></li>
                    <li class="nav-item"><a class="nav-link" href="/buttons">مدیریت منوها</a></li>
                    <li class="nav-item"><a class="nav-link" href="/settings">تنظیمات و ریست</a></li>
                    <li class="nav-item"><a class="nav-link text-danger" href="/logout">خروج</a></li>
                </ul>
            </div>
        </div>
    </nav>
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

@app.route('/health')
def health_check():
    return "OK", 200

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == PANEL_USER and request.form['password'] == PANEL_PASS:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        flash('نام کاربری یا رمز عبور اشتباه است.', 'danger')
    html = """
    <!DOCTYPE html><html lang="fa" dir="rtl"><head><meta charset="UTF-8"><title>ورود</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head><body class="bg-light"><div class="container mt-5" style="max-width: 400px;">
    <div class="card shadow"><div class="card-header bg-primary text-white text-center">ورود به مدیریت</div>
    <div class="card-body"><form method="POST">
    <input type="text" name="username" class="form-control mb-3" placeholder="نام کاربری" required>
    <input type="password" name="password" class="form-control mb-3" placeholder="رمز عبور" required>
    <button class="btn btn-primary w-100" type="submit">ورود</button>
    </form></div></div></div></body></html>
    """
    return render_template_string(html)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    users = database.get_all_users()
    html = BASE_TEMPLATE + """
    {% block content %}
    <h2>داشبورد</h2>
    <div class="row mt-4">
        <div class="col-md-4">
            <div class="card text-white bg-info mb-3"><div class="card-body">
            <h5 class="card-title">تعداد کاربران</h5><p class="card-text fs-2">{{ count }}</p>
            </div></div>
        </div>
    </div>
    <a href="/backup" class="btn btn-success">📥 دانلود بک‌آپ دیتابیس</a>
    {% endblock %}
    """
    return render_template_string(html, count=len(users))

@app.route('/users')
@login_required
def users_page():
    users = database.get_all_users()
    html = BASE_TEMPLATE + """
    {% block content %}
    <h2>لیست کاربران</h2>
    <table class="table table-striped mt-3">
        <thead><tr><th>آیدی تلگرام</th><th>نام کاربری</th><th>نام کامل</th><th>تاریخ عضویت</th></tr></thead>
        <tbody>
        {% for u in users %}
            <tr><td>{{ u.user_id }}</td><td>{{ u.username }}</td><td>{{ u.full_name }}</td><td>{{ u.joined_at }}</td></tr>
        {% endfor %}
        </tbody>
    </table>
    {% endblock %}
    """
    return render_template_string(html, users=users)

@app.route('/buttons')
@login_required
def buttons_page():
    buttons = database.get_buttons(0, admin_mode=True)
    html = BASE_TEMPLATE + """
    {% block content %}
    <h2>مدیریت دکمه‌های اصلی</h2>
    <ul class="list-group mt-3">
    {% for b in buttons %}
        <li class="list-group-item">{{ b.title }}</li>
    {% endfor %}
    </ul>
    <p class="mt-3 text-muted">* جهت افزودن دکمه‌های تودرتو و فایل از ربات تلگرام (دستور admin/) استفاده کنید.</p>
    {% endblock %}
    """
    return render_template_string(html, buttons=buttons)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        database.update_setting('welcome_text', request.form.get('welcome_text'))
        database.update_setting('contact_text', request.form.get('contact_text'))
        flash("تنظیمات ذخیره شد.", "success")
        return redirect(url_for('settings'))
    
    welcome = database.get_setting('welcome_text')
    contact = database.get_setting('contact_text')
    
    html = BASE_TEMPLATE + """
    {% block content %}
    <h2>تنظیمات ربات</h2>
    <form method="POST" class="mt-3">
        <div class="mb-3">
            <label>متن خوش‌آمدگویی:</label>
            <textarea name="welcome_text" class="form-control" rows="3">{{ welcome }}</textarea>
        </div>
        <div class="mb-3">
            <label>متن تماس با ما:</label>
            <textarea name="contact_text" class="form-control" rows="3">{{ contact }}</textarea>
        </div>
        <button type="submit" class="btn btn-primary">ذخیره تنظیمات متن</button>
    </form>

    <hr class="my-5">

    <div class="card border-danger mb-5">
        <div class="card-header bg-danger text-white font-weight-bold">
            ⚠️ منطقه خطر - بازنشانی سیستم (Factory Reset)
        </div>
        <div class="card-body">
            <p class="card-text text-muted">
                با کلیک روی این دکمه، تمامی <strong>دکمه‌های منو</strong>، <strong>کاتالوگ‌ها و تصاویر</strong> و <strong>تنظیمات</strong> پاک شده و به حالت اولیه کارخانه بازمی‌گردند. (لیست کاربران باقی خواهد ماند).
            </p>
            <form action="/reset_config" method="POST" onsubmit="return confirm('⚠️ آیا از بازنشانی کامل دکمه‌ها، کاتالوگ‌ها و تنظیمات اطمینان کامل دارید؟ این عملیات قابل بازگشت نیست!');">
                <button type="submit" class="btn btn-danger font-weight-bold">
                    🗑️ بازنشانی کامل سیستم
                </button>
            </form>
        </div>
    </div>
    {% endblock %}
    """
    return render_template_string(html, welcome=welcome, contact=contact)

@app.route('/reset_config', methods=['POST'])
@login_required
def reset_config_route():
    success = database.reset_bot_config()
    if success:
        flash("تمامی دکمه‌ها، کاتالوگ‌ها و تنظیمات با موفقیت ریست شدند و به حالت اولیه بازگشتند.", "success")
    else:
        flash("خطا در بازنشانی اطلاعات به حالت اولیه.", "danger")
    return redirect(url_for('settings'))

@app.route('/backup')
@login_required
def backup():
    return send_file(database.DB_PATH, as_attachment=True)
