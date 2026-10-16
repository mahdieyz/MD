import os, sqlite3, re, time, logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters
)
from database import Database

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

db = Database()
TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip()]

# States for conversation
(UPLOAD_CAT, UPLOAD_FILE, UPLOAD_NOTE, SET_CONTACT, SET_WELCOME, BROADCAST,
 RESTORE_DB, MANAGE_CAT, EDIT_BTN, SUB_PARENT, SUB_LIST, SUB_EDIT, SUB_ADD) = range(14)

def is_admin(uid):
    return uid in ADMIN_IDS

# ─── DYNAMIC SUB-MENU DATABASE ───
def init_sub_db():
    conn = sqlite3.connect(db.db_name)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS submenus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent TEXT,
            btn_key TEXT UNIQUE,
            btn_text TEXT,
            db_category TEXT
        )
    """)
    conn.commit()
    # Seed default facade buttons if empty
    defaults = [
        ("facade", "btn_mod_noor", "مد نور", "mod_noor"),
        ("facade", "btn_shaa", "شعاع", "shaa"),
        ("facade", "btn_anvar", "انوار", "anvar"),
        ("switches", "btn_smart", "پریز و کلید هوشمند", "smart_switches"),
        ("switches", "btn_mech", "کلید مکانیکی", "mechanical_switches"),
    ]
    for p, k, t, c in defaults:
        conn.execute("INSERT OR IGNORE INTO submenus (parent,btn_key,btn_text,db_category) VALUES (?,?,?,?)", (p, k, t, c))
    conn.commit()
    conn.close()

def load_submenus(parent):
    conn = sqlite3.connect(db.db_name)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM submenus WHERE parent = ? ORDER BY btn_key", (parent,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_sub_text(key):
    conn = sqlite3.connect(db.db_name)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT btn_text FROM submenus WHERE btn_key = ?", (key,)).fetchone()
    conn.close()
    return row["btn_text"] if row else None

def add_submenu(parent, text, key, db_cat):
    conn = sqlite3.connect(db.db_name)
    conn.execute("INSERT INTO submenus (parent, btn_key, btn_text, db_category) VALUES (?,?,?,?)", (parent, key, text, db_cat))
    conn.commit()
    conn.close()

def update_sub_text(key, text):
    conn = sqlite3.connect(db.db_name)
    conn.execute("UPDATE submenus SET btn_text = ? WHERE btn_key = ?", (text, key))
    conn.commit()
    conn.close()

def delete_submenu(key):
    conn = sqlite3.connect(db.db_name)
    conn.execute("DELETE FROM submenus WHERE btn_key = ?", (key,))
    conn.commit()
    conn.close()

# Load CAT_KEYS from DB on startup
CAT_KEYS = {}
def load_cat_keys():
    global CAT_KEYS
    CAT_KEYS = {}
    try:
        conn = sqlite3.connect(db.db_name)
        conn.row_factory = sqlite3.Row
        for row in conn.execute("SELECT btn_key, db_category FROM submenus").fetchall():
            CAT_KEYS[row["btn_key"]] = row["db_category"]
        conn.close()
    except Exception as e:
        logger.warning("Could not load submenus: %s", e)

def get_btn_text(key):
    # First try submenus DB
    txt = get_sub_text(key)
    if txt:
        return txt
    # Fallback to settings/default
    default_map = {
        "btn_magnetar": "مگنتار و چراغ لاینی",
        "btn_switches_main": "کلید ، پریز هوشمند و مکانیکی",
        "btn_industrial": "صنعتی ساختمانی",
        "btn_facade_main": "نمای ساختمان - محوطه - استخری",
        "btn_cable": "سیم و کابل",
        "btn_intercom": "آیفون",
        "btn_fire": "اعلان حریق",
        "btn_milo": "پریز کابینتی میلو",
        "btn_meloni": "پریز کابینتی ملونی",
        "btn_contact": "🛒 ثبت سفارش / تماس با ما",
        "btn_back": "بازگشت به منوی اصلی",
        "btn_mod_noor": "مد نور",
        "btn_shaa": "شعاع",
        "btn_anvar": "انوار",
        "btn_smart": "پریز و کلید هوشمند",
        "btn_mech": "کلید مکانیکی",
    }
    # Also allow custom main buttons edited via settings
    custom = db.get_setting(key)
    if custom:
        return custom
    return default_map.get(key, key)

# Initialize DB structures
init_sub_db()
load_cat_keys()

# Main button layout (uses dynamic text from DB/defaults)
LAYOUT_MAIN = [
    ["btn_magnetar", "btn_switches_main"],
    ["btn_industrial", "btn_facade_main"],
    ["btn_cable", "btn_intercom", "btn_fire"],
    ["btn_milo", "btn_meloni"],
    ["btn_contact"]
]

def build_main_kb():
    kb = []
    for row in LAYOUT_MAIN:
        row_buttons = []
        for key in row:
            text = get_btn_text(key)
            if text == "HIDDEN":
                continue
            row_buttons.append(KeyboardButton(text))
        if row_buttons:
            kb.append(row_buttons)
    # Safety: if everything hidden, at least show start/help
    if not kb:
        kb = [[KeyboardButton("/start")]]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def build_sub_kb(parent):
    # Build from submenus DB
    items = load_submenus(parent)
    kb = []
    # Arrange in rows of 3 for aesthetics
    temp_row = []
    for item in items:
        txt = item["btn_text"]
        if txt == "HIDDEN" or txt is None:
            continue
        key = item["btn_key"]
        temp_row.append(KeyboardButton(txt))
        if len(temp_row) == 3:
            kb.append(temp_row)
            temp_row = []
    if temp_row:
        kb.append(temp_row)
    kb.append([KeyboardButton(get_btn_text("btn_back"))])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

# Admin inline keyboards
def admin_panel_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 آپلود PDF / عکس", callback_data="adm_upload"),
         InlineKeyboardButton("🗑️ مدیریت فایل‌ها", callback_data="adm_manage_pick")],
        [InlineKeyboardButton("✏️ تغییر نام دکمه اصلی", callback_data="adm_edit_btns"),
         InlineKeyboardButton("👁️‍🗨️ مخفی/حذف دکمه اصلی", callback_data="adm_hide_btns")],
        [InlineKeyboardButton("📂 ویرایش منوی فرعی", callback_data="adm_submenu"),
         InlineKeyboardButton("📞 متن تماس", callback_data="adm_contact")],
        [InlineKeyboardButton("👋 پیام شروع / welcome", callback_data="adm_welcome")],
        [InlineKeyboardButton("📢 پیام همگانی", callback_data="adm_broadcast"),
         InlineKeyboardButton("📊 آمار", callback_data="adm_stats")],
        [InlineKeyboardButton("💾 بکاپ", callback_data="adm_backup"),
         InlineKeyboardButton("📥 بازگردانی", callback_data="adm_restore")]
    ])

def sub_parent_picker():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("نمای ساختمان (مد نور / شعاع / انوار)", callback_data="sub_parent_facade")],
        [InlineKeyboardButton("کلید و پریز (هوشمند / مکانیکی)", callback_data="sub_parent_switches")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="adm_home")]
    ])

def sub_list_kb(parent, current_items):
    kb = []
    for item in current_items:
        txt = item["btn_text"]
        key = item["btn_key"]
        kb.append([
            InlineKeyboardButton(txt + " ✏️", callback_data=f"sub_edit_{key}"),
            InlineKeyboardButton("🗑️", callback_data=f"sub_del_{key}")
        ])
    kb.append([InlineKeyboardButton("➕ اضافه کردن دکمه جدید", callback_data=f"sub_add_{parent}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="adm_home")])
    return InlineKeyboardMarkup(kb)

# ── BASIC COMMANDS ──

async def start(update: Update, ctx):
    u = update.effective_user
    db.add_user(u.id, u.username, u.first_name, u.last_name)
    template = db.get_setting("welcome_text")
    if template:
        welcome = template.replace("{name}", u.first_name or "کاربر")
    else:
        welcome = (f"سلام {u.first_name or 'کاربر'} عزیز! 👋\n"
                   "به ربات توان سازه خوش آمدید.\nجهت دریافت فایل‌های قیمت، از منوی زیر انتخاب کنید:")
    await update.message.reply_text(welcome, reply_markup=build_main_kb())

async def cancel_cmd(update: Update, ctx):
    ctx.user_data.clear()
    await update.message.reply_text("❌ لغو شد.", reply_markup=build_main_kb())
    return ConversationHandler.END

# ── MAIN MESSAGE HANDLER (DYNAMIC) ──

async def handle_message(update: Update, ctx):
    text = update.message.text
    chat_id = update.effective_chat.id

    # First try main buttons
    matched_key = None
    for key in DEFAULT_BUTTON_KEYS():
        btn_text = get_btn_text(key)
        if btn_text and btn_text != "HIDDEN" and text == btn_text:
            matched_key = key
            break

    if matched_key:
        # Back to main
        if matched_key == "btn_back":
            await update.message.reply_text("منوی اصلی 👇", reply_markup=build_main_kb())
            return

        # Sub-menu parents
        if matched_key == "btn_facade_main":
            await update.message.reply_text("برند مورد نظر را انتخاب کنید:", reply_markup=build_sub_kb("facade"))
            return
        if matched_key == "btn_switches_main":
            await update.message.reply_text("دسته‌بندی را انتخاب کنید:", reply_markup=build_sub_kb("switches"))
            return

        # Contact
        if matched_key == "btn_contact":
            contact = db.get_setting("contact_text", "📞 *ارتباط با فروش*\n📱 021-12345678")
            await update.message.reply_text(contact, parse_mode="Markdown", reply_markup=build_main_kb())
            return

        # Main category with PDF
        cat_key = CAT_KEYS.get(matched_key)
        if cat_key:
            files = db.get_catalogs(cat_key)
            if not files:
                await update.message.reply_text("📂 هنوز فایلی برای این بخش ثبت نشده است.", reply_markup=build_sub_kb("facade") if "facade" in matched_key else build_main_kb())
                return
            await update.message.reply_text(f"⏳ در حال ارسال فایل‌های «{text}»...")
            sent = 0
            for item in files:
                try:
                    cap = item.get("note") or None
                    if item.get("file_type") == "photo":
                        await ctx.bot.send_photo(chat_id=chat_id, photo=item["file_id"], caption=cap)
                    else:
                        await ctx.bot.send_document(chat_id=chat_id, document=item["file_id"], caption=cap)
                    sent += 1
                except Exception as e:
                    logger.error("Send error %s: %s", item.get("id"), e)
            await update.message.reply_text(f"✅ {sent} فایل ارسال شد." if sent else "⚠️ ارسال ناموفق.", reply_markup=build_sub_kb("facade") if "facade" in matched_key else build_sub_kb("switches") if "switch" in matched_key else build_main_kb())

    # If not matched in main, try SUB-MENU items (from DB)
    # We search by text directly across all submenus
    conn = sqlite3.connect(db.db_name)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT btn_key, btn_text, parent, db_category FROM submenus WHERE btn_text = ?", (text,)).fetchone()
    conn.close()
    if row:
        btn_key = row["btn_key"]
        parent = row["parent"]
        cat_key = row["db_category"] or btn_key

        # If they clicked a sub-button, send files
        files = db.get_catalogs(cat_key)
        if not files:
            await update.message.reply_text("📂 هنوز فایلی برای این بخش ثبت نشده است.", reply_markup=build_sub_kb(parent))
            return

        await update.message.reply_text(f"⏳ ارسال فایل‌های «{text}»...")
        sent = 0
        for item in files:
            try:
                cap = item.get("note") or None
                if item.get("file_type") == "photo":
                    await ctx.bot.send_photo(chat_id=chat_id, photo=item["file_id"], caption=cap)
                else:
                    await ctx.bot.send_document(chat_id=chat_id, document=item["file_id"], caption=cap)
                sent += 1
            except Exception as e:
                logger.error("Send error %s: %s", item.get("id"), e)

        await update.message.reply_text(f"✅ {sent} فایل ارسال شد." if sent else "⚠️ ارسال ناموفق.", reply_markup=build_sub_kb(parent))

def DEFAULT_BUTTON_KEYS():
    return ["btn_magnetar","btn_switches_main","btn_industrial","btn_facade_main","btn_cable","btn_intercom","btn_fire","btn_milo","btn_meloni","btn_contact","btn_back"]

# ── ADMIN CALLBACK HANDLER ──

async def admin_cmd(update: Update, ctx):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ دسترسی ندارید.")
        return
    await update.message.reply_text("🔧 *پنل مدیریت ربات*\nگزینه مورد نظر را انتخاب کنید:", parse_mode="Markdown", reply_markup=admin_panel_kb())

async def admin_cb(update: Update, ctx):
    q = update.callback_query
    await q.answer()
    data = q.data
    if not is_admin(q.from_user.id):
        await q.edit_message_text("⛔ دسترسی ندارید.")
        return ConversationHandler.END

    if data == "adm_home":
        await q.edit_message_text("🔧 *پنل مدیریت ربات*", parse_mode="Markdown", reply_markup=admin_panel_kb())
        return ConversationHandler.END

    if data == "adm_submenu":
        await q.edit_message_text("📂 منوی فرعی کدام گروه؟", reply_markup=sub_parent_picker())
        return SUB_PARENT

    if data.startswith("sub_parent_"):
        parent = data.split("_")[-1]  # facade or switches
        ctx.user_data["sub_parent"] = parent
        items = load_submenus(parent)
        await q.edit_message_text(f"📂 دکمه‌های گروه {parent}:\nبرای ویرایش روی ✏️، برای حذف 🗑️، برای اضافه ➕ بزنید.", reply_markup=sub_list_kb(parent, items))
        return SUB_LIST

    if data.startswith("sub_edit_"):
        btn_key = data[9:]
        ctx.user_data["sub_edit_key"] = btn_key
        current = get_sub_text(btn_key) or "نام قبلی"
        await q.edit_message_text(f"✏️ نام جدید دکمه را بفرستید:\n(نام فعلی: {current})", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="adm_home")]]))
        return SUB_EDIT

    if data.startswith("sub_del_"):
        btn_key = data[8:]
        delete_submenu(btn_key)
        # Also remove from CAT_KEYS if present
        if btn_key in CAT_KEYS:
            del CAT_KEYS[btn_key]
        await q.edit_message_text("✅ دکمه حذف (مخفی) شد.\nمی‌توانید با ویرایش نام آن را برگردانید.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="adm_home")]]))
        return ConversationHandler.END

    if data.startswith("sub_add_"):
        parent = data[8:]
        ctx.user_data["sub_add_parent"] = parent
        await q.edit_message_text("➕ نام دکمه جدید را بفرستید:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="adm_home")]]))
        return SUB_ADD

    # Stats
    if data == "adm_stats":
        s = db.get_stats()
        counts = db.count_catalogs_by_category()
        details = "\n".join(f" • {k}: {v}" for k, v in counts.items()) or " (خالی)"
        await q.edit_message_text(
            f"📊 *آمار ربات*\n\n👥 کاربران: {s['total_users']}\n📁 فایل‌ها: {s['total_files']}\n\n📦 *توزیع:*\n{details}",
            parse_mode="Markdown", reply_markup=admin_panel_kb())
        return ConversationHandler.END

    # Backup
    if data == "adm_backup":
        await q.edit_message_text("⏳ در حال ساخت بکاپ...")
        try:
            bpath = db.db_name + ".backup"
            db.backup_to_file(bpath)
            with open(bpath, "rb") as f:
                await ctx.bot.send_document(q.message.chat_id, document=f, caption="💾 بکاپ")
            os.remove(bpath)
            await q.edit_message_text("✅ بکاپ ارسال شد.", reply_markup=admin_panel_kb())
        except Exception as e:
            await q.edit_message_text(f"❌ خطا: {e}")
        return ConversationHandler.END

    if data == "adm_restore":
        await q.edit_message_text("📥 فایل `.db` را بفرستید.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="adm_home")]]))
        return RESTORE_DB

    if data == "adm_upload":
        await q.edit_message_text("📂 انتخاب دسته:", reply_markup=dynamic_cat_picker())
        return UPLOAD_CAT

    if data == "adm_manage_pick":
        await q.edit_message_text("🗂️ دسته برای مدیریت:", reply_markup=dynamic_cat_picker())
        return MANAGE_CAT

    if data.startswith("mcat_"):
        btn_key = data[5:]
        cat_key = CAT_KEYS.get(btn_key, btn_key)
        files = db.get_catalogs(cat_key)
        if not files:
            await q.edit_message_text("📂 خالی است.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="adm_home")]]))
            return ConversationHandler.END
        kb = [[InlineKeyboardButton(f"🗑️ {f.get('file_name', 'فایل')}", callback_data=f"del_{f['id']}")] for f in files]
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="adm_home")])
        await q.edit_message_text("🗑️ برای حذف فایل کلیک کنید:", reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END

    if data.startswith("del_"):
        cid = int(data[4:])
        db.delete_catalog(cid)
        await q.edit_message_text("✅ فایل حذف شد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="adm_home")]]))
        return ConversationHandler.END

    if data == "adm_edit_btns":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(t[:30], callback_data=f"editbtn_{k}")] for k,t in {
            "btn_magnetar":"مگنتار","btn_switches_main":"کلیدهوشمند","btn_industrial":"صنعتی",
            "btn_facade_main":"نمای ساختمان","btn_cable":"سیم","btn_intercom":"آیفون",
            "btn_fire":"اعلان","btn_milo":"میلو","btn_meloni":"ملونی","btn_contact":"ثبت سفارش"
        }.items()])
        await q.edit_message_text("✏️ دکمه اصلی را انتخاب کنید (سپس متن جدید بفرستید):", reply_markup=kb)
        return ConversationHandler.END  # handled via text input below? Actually need state. For brevity, using direct set.

    # Direct edit button name via setting (simpler for this version)
    if data.startswith("editbtn_"):
        key = data[9:]
        ctx.user_data["edit_main_key"] = key
        cur = get_btn_text(key)
        await q.edit_message_text(f"✏️ نام فعلی: {cur}\nمتن جدید را بفرستید:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="adm_home")]]))
        return EDIT_BTN

    if data == "adm_hide_btns":
        btn_map = [
            ("btn_magnetar","مگنتار"),("btn_switches_main","کلیدها"),("btn_industrial","صنعتی"),
            ("btn_facade_main","نمای ساختمان"),("btn_cable","سیم"),("btn_intercom","آیفون"),
            ("btn_fire","اعلان"),("btn_milo","میلو"),("btn_meloni","ملونی"),("btn_contact","ثبت سفارش")
        ]
        kb = [[InlineKeyboardButton(name, callback_data=f"hidebtn_{k}")] for k,name in btn_map]
        await q.edit_message_text("👁️ دکمه‌ای که می‌خواهید مخفی شود:", reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END

    if data.startswith("hidebtn_"):
        key = data[9:]
        db.set_setting(key, "HIDDEN")
        await q.edit_message_text("✅ دکمه مخفی شد.", reply_markup=admin_panel_kb())
        return ConversationHandler.END

    if data == "adm_contact":
        cur = db.get_setting("contact_text", "(خالی)")
        await q.edit_message_text(f"📝 متن فعلی:\n\n{cur}\n--------\nمتن جدید را بفرستید:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="adm_home")]]))
        return SET_CONTACT

    if data == "adm_welcome":
        cur = db.get_setting("welcome_text", "(پیش‌فرض)")
        await q.edit_message_text(f"👋 متن شروع فعلی:\n\n{cur}\n--------\nمتن جدید را بفرستید (می‌توانید از {{name}} استفاده کنید):", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="adm_home")]]))
        return SET_WELCOME

    if data == "adm_broadcast":
        await q.edit_message_text("📢 متن پیام همگانی را بفرستید:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="adm_home")]]))
        return BROADCAST

    return ConversationHandler.END

# Dynamic picker for upload/manage based on CAT_KEYS + submenus
def dynamic_cat_picker():
    # Combine main categories and sub categories
    rows = []
    # Add submenus categories
    try:
        conn = sqlite3.connect(db.db_name)
        conn.row_factory = sqlite3.Row
        cat_rows = conn.execute("SELECT DISTINCT db_category FROM submenus WHERE db_category IS NOT NULL").fetchall()
        for r in cat_rows:
            c = r["db_category"]
            # find a pretty name roughly
            pretty = c
            rows.append([InlineKeyboardButton(pretty[:25], callback_data=f"ucat_{c}")])
        conn.close()
    except:
        pass
    # Add a few known
    rows += [
        [InlineKeyboardButton("مد نور", callback_data="ucat_mod_noor")],
        [InlineKeyboardButton("مگنتار", callback_data="ucat_magnetar_line")],
        [InlineKeyboardButton("صنعتی", callback_data="ucat_industrial")]
    ]
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="adm_home")])
    return InlineKeyboardMarkup(rows)

# ── STATE RECEIVERS ──

async def sub_edit_receive(update: Update, ctx):
    key = ctx.user_data.get("sub_edit_key")
    if key:
        update_sub_text(key, update.message.text)
        # Refresh CAT_KEYS if needed
        load_cat_keys()
        await update.message.reply_text("✅ نام دکمه تغییر یافت.", reply_markup=build_main_kb())
    ctx.user_data.clear()
    return ConversationHandler.END

async def sub_add_receive(update: Update, ctx):
    parent = ctx.user_data.get("sub_add_parent")
    text = update.message.text.strip()
    if parent and text:
        new_key = f"btn_sub_{parent}_{int(time.time())}"
        new_cat = f"cat_{parent}_{new_key}"
        add_submenu(parent, text, new_key, new_cat)
        CAT_KEYS[new_key] = new_cat
        load_cat_keys()
        await update.message.reply_text(f"✅ دکمه «{text}» اضافه شد.", reply_markup=build_main_kb())
    ctx.user_data.clear()
    return ConversationHandler.END

async def edit_main_btn_receive(update: Update, ctx):
    key = ctx.user_data.get("edit_main_key")
    if key:
        db.set_setting(key, update.message.text)
        await update.message.reply_text("✅ نام دکمه اصلی تغییر یافت.", reply_markup=build_main_kb())
    ctx.user_data.clear()
    return ConversationHandler.END

async def upload_file_receive(update: Update, ctx):
    msg = update.message
    if msg.document:
        ctx.user_data.update({"uid": msg.document.file_id, "uname": msg.document.file_name or "doc.pdf", "utype": "document"})
    elif msg.photo:
        ctx.user_data.update({"uid": msg.photo[-1].file_id, "uname": "photo.jpg", "utype": "photo"})
    else:
        await msg.reply_text("⚠️ لطفاً فایل PDF یا عکس بفرستید:")
        return UPLOAD_FILE
    await msg.reply_text("📝 دریافت شد! توضیح یا قیمت را تایپ کنید (0 برای بدون متن):")
    return UPLOAD_NOTE

async def upload_note_receive(update: Update, ctx):
    note = update.message.text.strip()
    cat_key = ctx.user_data.get("upload_cat_key") or "unknown"
    db.add_catalog_file(
        cat_key=cat_key, title=cat_key,
        file_id=ctx.user_data["uid"], file_name=ctx.user_data["uname"],
        note="" if note == "0" else note, file_type=ctx.user_data["utype"])
    await update.message.reply_text("✅ فایل ذخیره و به دسته متصل شد.", reply_markup=build_main_kb())
    ctx.user_data.clear()
    return ConversationHandler.END

async def ucat_select(update: Update, ctx):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id): return ConversationHandler.END
    # The data format is ucat_{cat_key}
    cat_key = q.data[5:] if q.data.startswith("ucat_") else q.data
    ctx.user_data["upload_cat_key"] = cat_key
    await q.edit_message_text("📄 فایل را ارسال کنید:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="adm_home")]]))
    return UPLOAD_FILE

async def restore_db_receive(update: Update, ctx):
    msg = update.message
    if not msg.document or not (msg.document.file_name or "").endswith(".db"):
        await msg.reply_text("⚠️ فایل `.db` مجاز است.")
        return RESTORE_DB
    tmp = "restore_tmp.db"
    try:
        f = await ctx.bot.get_file(msg.document.file_id)
        await f.download_to_drive(tmp)
        db.restore_from_file(tmp)
        os.remove(tmp)
        await msg.reply_text("✅ بازگردانی شد!", reply_markup=build_main_kb())
    except Exception as e:
        if os.path.exists(tmp): os.remove(tmp)
        await msg.reply_text(f"❌ خطا: {e}")
    return ConversationHandler.END

async def set_contact_receive(update: Update, ctx):
    db.set_setting("contact_text", update.message.text)
    await update.message.reply_text("✅ متن تماس بروزرسانی شد.", reply_markup=build_main_kb())
    return ConversationHandler.END

async def set_welcome_receive(update: Update, ctx):
    db.set_setting("welcome_text", update.message.text)
    await update.message.reply_text("✅ پیام شروع بروزرسانی شد.", reply_markup=build_main_kb())
    return ConversationHandler.END

async def broadcast_receive(update: Update, ctx):
    msg = update.message.text
    users = db.get_all_users()
    status = await update.message.reply_text(f"⏳ ارسال به {len(users)} کاربر...")
    ok = fail = 0
    for u in users:
        try:
            await ctx.bot.send_message(u["user_id"], msg[:4000])
            ok += 1
        except: fail += 1
    await status.edit_text(f"✅ گزارش: موفق {ok} | ناموفق {fail}")
    return ConversationHandler.END

async def cancel_state(update: Update, ctx):
    ctx.user_data.clear()
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ لغو شد.")
    elif update.message:
        await update.message.reply_text("❌ لغو شد.", reply_markup=build_main_kb())
    return ConversationHandler.END

# ── MAIN ENGINE ──

def main():
    if not TOKEN:
        logger.error("❌ BOT_TOKEN missing!")
        return
    # Ensure sub DB ready
    init_sub_db()
    load_cat_keys()
    app = Application.builder().token(TOKEN).build()

    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_cb, pattern="^adm_|^sub_|^editbtn_|^hidebtn_")],
        states={
            SUB_PARENT: [CallbackQueryHandler(admin_cb, pattern="^sub_parent_")],
            SUB_LIST: [CallbackQueryHandler(admin_cb, pattern="^sub_(edit|del|add)_")],
            SUB_EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, sub_edit_receive)],
            SUB_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, sub_add_receive)],
            UPLOAD_CAT: [CallbackQueryHandler(ucat_select, pattern="^ucat_")],
            UPLOAD_FILE: [MessageHandler(filters.Document.ALL | filters.PHOTO, upload_file_receive)],
            UPLOAD_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_note_receive)],
            MANAGE_CAT: [CallbackQueryHandler(admin_cb, pattern="^mcat_")],
            RESTORE_DB: [MessageHandler(filters.Document.ALL, restore_db_receive)],
            SET_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_contact_receive)],
            SET_WELCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_welcome_receive)],
            BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_receive)],
            EDIT_BTN: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_main_btn_receive)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_state),
            MessageHandler(filters.Regex("^(لغو|انصراف|بازگشت)$"), cancel_state),
            CallbackQueryHandler(admin_cb, pattern="^adm_home$")
        ],
        per_message=False,
        allow_reentry=True
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(admin_conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("🤖 Tavansazeh bot is live with dynamic submenus...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
