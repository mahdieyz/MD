import os, re, logging
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

(UPLOAD_CAT, UPLOAD_FILE, UPLOAD_NOTE, SET_CONTACT, BROADCAST, 
 RESTORE_DB, MANAGE_CAT, EDIT_BTN) = range(8)

def is_admin(uid):
    return uid in ADMIN_IDS

# ── DYNAMIC BUTTON SYSTEM ──

# Default text for buttons
DEFAULT_BUTTONS = {
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
    "btn_mod_noor": "مد نور",
    "btn_shaa": "شعاع",
    "btn_anvar": "انوار",
    "btn_smart": "پریز و کلید هوشمند",
    "btn_mech": "کلید مکانیکی",
    "btn_back": "بازگشت به منوی اصلی"
}

# Link button IDs to internal database category keys for PDFs
CAT_KEYS = {
    "btn_magnetar": "magnetar_line",
    "btn_industrial": "industrial",
    "btn_cable": "wire_cable",
    "btn_intercom": "intercom",
    "btn_fire": "fire_alarm",
    "btn_milo": "milo_socket",
    "btn_meloni": "meloni_socket",
    "btn_mod_noor": "mod_noor",
    "btn_shaa": "shaa",
    "btn_anvar": "anvar",
    "btn_smart": "smart_switches",
    "btn_mech": "mechanical_switches"
}

# Keyboard Layouts
LAYOUT_MAIN = [
    ["btn_magnetar", "btn_switches_main"],
    ["btn_industrial", "btn_facade_main"],
    ["btn_cable", "btn_intercom", "btn_fire"],
    ["btn_milo", "btn_meloni"],
    ["btn_contact"]
]
LAYOUT_FACADE = [["btn_mod_noor", "btn_shaa", "btn_anvar"], ["btn_back"]]
LAYOUT_SWITCHES = [["btn_smart", "btn_mech"], ["btn_back"]]

def get_btn(key):
    """Fetch the custom name. If hidden, returns 'HIDDEN'"""
    return db.get_setting(key, DEFAULT_BUTTONS.get(key, ""))

def build_reply_kb(layout_matrix):
    """Dynamically builds a Telegram keyboard, skipping deleted/hidden buttons."""
    kb = []
    for row in layout_matrix:
        kb_row = []
        for key in row:
            text = get_btn(key)
            if text and text != "HIDDEN":
                kb_row.append(KeyboardButton(text))
        if kb_row:  # Only add row if it's not empty
            kb.append(kb_row)
    
    if not kb:
        # Failsafe if everything is deleted
        return ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True)
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

# ── INLINE KEYBOARDS (ADMIN) ──

def admin_panel_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 آپلود PDF / عکس", callback_data="adm_upload")],
        [InlineKeyboardButton("🗑️ مدیریت فایل‌ها", callback_data="adm_manage_pick"),
         InlineKeyboardButton("📞 متن تماس", callback_data="adm_contact")],
        [InlineKeyboardButton("✏️ تغییر نام دکمه", callback_data="adm_edit_btns"),
         InlineKeyboardButton("👁️‍🗨️ مخفی/حذف دکمه", callback_data="adm_hide_btns")],
        [InlineKeyboardButton("💾 بکاپ گیری", callback_data="adm_backup"),
         InlineKeyboardButton("📥 بازگردانی بکاپ", callback_data="adm_restore")],
        [InlineKeyboardButton("📢 پیام همگانی", callback_data="adm_broadcast"),
         InlineKeyboardButton("📊 آمار", callback_data="adm_stats")]
    ])

def dynamic_picker_kb(prefix, mode="cats_only"):
    """
    mode='cats_only' -> For Upload/Manage (only shows categories in CAT_KEYS)
    mode='all' -> For Renaming (shows everything so you can unhide)
    mode='hide' -> For Hiding (shows everything currently visible except back btn)
    """
    kb = []
    row = []
    
    keys_to_iterate = CAT_KEYS.keys() if mode == "cats_only" else DEFAULT_BUTTONS.keys()
    
    for key in keys_to_iterate:
        if mode == "hide" and key == "btn_back":
            continue # Don't allow hiding the back button

        current_name = get_btn(key)
        
        if mode == "hide" and current_name == "HIDDEN":
            continue # Already hidden
            
        display_text = current_name[:25] if current_name != "HIDDEN" else f"(مخفی) {DEFAULT_BUTTONS[key][:15]}"
        
        row.append(InlineKeyboardButton(display_text, callback_data=f"{prefix}{key}"))
        if len(row) == 2:
            kb.append(row)
            row = []
    
    if row:
        kb.append(row)
    kb.append([InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="adm_home")])
    return InlineKeyboardMarkup(kb)


# ── BASIC COMMANDS ──

async def start(update: Update, ctx):
    u = update.effective_user
    db.add_user(u.id, u.username, u.first_name, u.last_name)
    template = db.get_setting("welcome_text")
    welcome = template.replace("{name}", u.first_name or "کاربر") if template else (
        f"سلام {u.first_name or 'کاربر'} عزیز! 👋\n"
        "به ربات توان سازه خوش آمدید.\nجهت دریافت کاتالوگ، از منوی زیر استفاده کنید:"
    )
    await update.message.reply_text(welcome, reply_markup=build_reply_kb(LAYOUT_MAIN))

async def cancel_cmd(update: Update, ctx):
    ctx.user_data.clear()
    await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=build_reply_kb(LAYOUT_MAIN))
    return ConversationHandler.END

# ── MAIN MESSAGE HANDLER ──

async def handle_message(update: Update, ctx):
    text = update.message.text
    chat_id = update.effective_chat.id

    # 1. Match the user's text to a button key
    matched_key = None
    for k in DEFAULT_BUTTONS.keys():
        btn_text = get_btn(k)
        if btn_text != "HIDDEN" and text == btn_text:
            matched_key = k
            break

    if not matched_key:
        return # Ignore random text

    # 2. Handle Menu Navigation
    if matched_key == "btn_back":
        await update.message.reply_text("منوی اصلی 👇", reply_markup=build_reply_kb(LAYOUT_MAIN))
        return

    if matched_key == "btn_facade_main":
        await update.message.reply_text("برند مورد نظر را انتخاب کنید:", reply_markup=build_reply_kb(LAYOUT_FACADE))
        return

    if matched_key == "btn_switches_main":
        await update.message.reply_text("دسته‌بندی را انتخاب کنید:", reply_markup=build_reply_kb(LAYOUT_SWITCHES))
        return

    if matched_key == "btn_contact":
        contact = db.get_setting("contact_text", "📞 *ارتباط با فروش*\n\n📲 تلفن: 021-12345678\n👤 پشتیبانی: @Admin")
        await update.message.reply_text(contact, parse_mode="Markdown", reply_markup=build_reply_kb(LAYOUT_MAIN))
        return

    # 3. Handle Catalog Requests
    if matched_key in CAT_KEYS:
        cat_key = CAT_KEYS[matched_key]
        files = db.get_catalogs(cat_key)
        if not files:
            await update.message.reply_text("📂 هنوز فایلی برای این بخش ثبت نشده است.", reply_markup=build_reply_kb([["btn_back"]]))
            return

        await update.message.reply_text(f"⏳ ارسال فایل‌های «{text}»...")
        sent = 0
        for item in files:
            try:
                caption = item.get("note") or None
                if item.get("file_type") == "photo":
                    await ctx.bot.send_photo(chat_id=chat_id, photo=item["file_id"], caption=caption)
                else:
                    await ctx.bot.send_document(chat_id=chat_id, document=item["file_id"], caption=caption)
                sent += 1
            except Exception as e:
                logger.error(f"Send fail for cat={cat_key}: {e}")

        await update.message.reply_text(f"✅ {sent} فایل ارسال شد." if sent else "⚠️ ارسال ناموفق.", reply_markup=build_reply_kb([["btn_back"]]))


# ── ADMIN PANEL & CALLBACKS ──

async def admin_cmd(update: Update, ctx):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ دسترسی ندارید.")
        return
    await update.message.reply_text("🔧 *پنل مدیریت*", parse_mode="Markdown", reply_markup=admin_panel_kb())

async def admin_cb(update: Update, ctx):
    q = update.callback_query
    await q.answer()
    data = q.data

    if not is_admin(q.from_user.id):
        return ConversationHandler.END

    if data == "adm_home":
        await q.edit_message_text("🔧 *پنل مدیریت*", parse_mode="Markdown", reply_markup=admin_panel_kb())
        return ConversationHandler.END

    if data == "adm_stats":
        s = db.get_stats()
        counts = db.count_catalogs_by_category()
        details = "\n".join(f" • {k}: {v}" for k, v in counts.items()) or " (خالی)"
        await q.edit_message_text(f"📊 *آمار ربات*\n\n👥 کاربران: {s['total_users']}\n📁 کل فایل‌ها: {s['total_files']}\n\n📦 *توزیع:*\n{details}", parse_mode="Markdown", reply_markup=admin_panel_kb())
        return ConversationHandler.END

    if data == "adm_upload":
        await q.edit_message_text("📂 انتخاب دسته برای آپلود:", reply_markup=dynamic_picker_kb("ucat_", "cats_only"))
        return UPLOAD_CAT

    if data == "adm_manage_pick":
        await q.edit_message_text("🗂️ دسته مورد نظر برای مدیریت فایل‌ها:", reply_markup=dynamic_picker_kb("mcat_", "cats_only"))
        return MANAGE_CAT

    if data == "adm_edit_btns":
        await q.edit_message_text("✏️ دکمه‌ای که می‌خواهید تغییر نام دهید انتخاب کنید\n(دکمه‌های مخفی را با تغییر نام برگردانید):", reply_markup=dynamic_picker_kb("ebtn_", "all"))
        return ConversationHandler.END

    if data == "adm_hide_btns":
        await q.edit_message_text("👁️‍🗨️ دکمه‌ای که می‌خواهید مخفی/حذف شود را انتخاب کنید:", reply_markup=dynamic_picker_kb("hbtn_", "hide"))
        return ConversationHandler.END

    # Handle actual Hide action
    if data.startswith("hbtn_"):
        btn_key = data[5:]
        db.set_setting(btn_key, "HIDDEN")
        await q.edit_message_text(f"✅ دکمه با موفقیت مخفی شد.\nکاربران دیگر آن را نمی‌بینند.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="adm_home")]]))
        return ConversationHandler.END

    # Handle actual Edit action start
    if data.startswith("ebtn_"):
        btn_key = data[5:]
        ctx.user_data["edit_btn_key"] = btn_key
        cur_name = get_btn(btn_key)
        await q.edit_message_text(f"✏️ نام فعلی: «{cur_name}»\n\nنام جدید را تایپ و ارسال کنید:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="adm_home")]]))
        return EDIT_BTN

    # Handle Manage Category File selection
    if data.startswith("mcat_"):
        btn_key = data[5:]
        cat_key = CAT_KEYS.get(btn_key)
        files = db.get_catalogs(cat_key)
        if not files:
            await q.edit_message_text("📂 این دسته خالی است.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="adm_home")]]))
            return ConversationHandler.END
        kb = [[InlineKeyboardButton(f"🗑️ {f.get('file_name', 'فایل')} - {f.get('note', '')[:10]}", callback_data=f"del_{f['id']}")] for f in files]
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="adm_home")])
        await q.edit_message_text("🗑️ برای حذف، روی فایل کلیک کنید:", reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END

    if data.startswith("del_"):
        cid = int(data[4:])
        db.delete_catalog(cid)
        await q.edit_message_text("✅ فایل حذف شد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="adm_home")]]))
        return ConversationHandler.END

    if data == "adm_contact":
        cur = db.get_setting("contact_text", "(خالی)")
        await q.edit_message_text(f"📝 متن فعلی:\n\n{cur}\n\n────────\nمتن جدید را بفرستید:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="adm_home")]]))
        return SET_CONTACT

    if data == "adm_broadcast":
        await q.edit_message_text("📢 متن پیام همگانی را بفرستید:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="adm_home")]]))
        return BROADCAST
        
    if data == "adm_backup":
        await q.edit_message_text("⏳ در حال ساخت بکاپ...")
        try:
            bpath = db.db_name + ".backup"
            db.backup_to_file(bpath)
            with open(bpath, "rb") as f:
                await ctx.bot.send_document(q.message.chat_id, document=f, caption="💾 بکاپ دیتابیس")
            os.remove(bpath)
            await q.edit_message_text("✅ بکاپ ارسال شد.", reply_markup=admin_panel_kb())
        except Exception as e:
            await q.edit_message_text(f"❌ خطا: {e}")
        return ConversationHandler.END

    if data == "adm_restore":
        await q.edit_message_text("📥 فایل `.db` را ارسال کنید.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="adm_home")]]))
        return RESTORE_DB

    return ConversationHandler.END

# ── STATE RECEIVERS ──

async def ucat_select(update: Update, ctx):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id): return ConversationHandler.END
    btn_key = q.data[5:]
    ctx.user_data["upload_cat_key"] = CAT_KEYS.get(btn_key)
    await q.edit_message_text(f"📄 فایل مورد نظر را ارسال کنید (PDF یا عکس):", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="adm_home")]]))
    return UPLOAD_FILE

async def upload_file_receive(update: Update, ctx):
    msg = update.message
    if msg.document:
        ctx.user_data.update({"uid": msg.document.file_id, "uname": msg.document.file_name or "doc.pdf", "utype": "document"})
    elif msg.photo:
        ctx.user_data.update({"uid": msg.photo[-1].file_id, "uname": "photo.jpg", "utype": "photo"})
    else:
        await msg.reply_text("⚠️ لطفاً فقط فایل PDF یا عکس بفرستید:")
        return UPLOAD_FILE

    await msg.reply_text("📝 دریافت شد! توضیح یا قیمت را تایپ کنید (یا عدد 0 برای بدون متن):")
    return UPLOAD_NOTE

async def upload_note_receive(update: Update, ctx):
    note = update.message.text.strip()
    db.add_catalog_file(
        cat_key=ctx.user_data["upload_cat_key"], title=ctx.user_data["upload_cat_key"],
        file_id=ctx.user_data["uid"], file_name=ctx.user_data["uname"],
        note="" if note == "0" else note, file_type=ctx.user_data["utype"])
    await update.message.reply_text("✅ فایل ذخیره شد!", reply_markup=build_reply_kb(LAYOUT_MAIN))
    ctx.user_data.clear()
    return ConversationHandler.END

async def edit_btn_receive(update: Update, ctx):
    new_text = update.message.text.strip()
    key = ctx.user_data.get("edit_btn_key")
    if key:
        db.set_setting(key, new_text)
        await update.message.reply_text(f"✅ نام دکمه به «{new_text}» تغییر یافت.", reply_markup=build_reply_kb(LAYOUT_MAIN))
    ctx.user_data.clear()
    return ConversationHandler.END

async def set_contact_receive(update: Update, ctx):
    db.set_setting("contact_text", update.message.text)
    await update.message.reply_text("✅ متن بروزرسانی شد.", reply_markup=build_reply_kb(LAYOUT_MAIN))
    return ConversationHandler.END

async def broadcast_receive(update: Update, ctx):
    users = db.get_all_users()
    msg = update.message.text
    status = await update.message.reply_text(f"⏳ ارسال به {len(users)} کاربر...")
    ok = fail = 0
    for u in users:
        try:
            await ctx.bot.send_message(u["user_id"], msg)
            ok += 1
        except: fail += 1
    await status.edit_text(f"✅ ارسال شد\nموفق: {ok} | ناموفق: {fail}")
    return ConversationHandler.END

async def restore_db_receive(update: Update, ctx):
    msg = update.message
    if not msg.document or not (msg.document.file_name or "").endswith(".db"):
        await msg.reply_text("⚠️ فقط فایل .db مجاز است.")
        return RESTORE_DB
    tmp = "restore_tmp.db"
    try:
        f = await ctx.bot.get_file(msg.document.file_id)
        await f.download_to_drive(tmp)
        db.restore_from_file(tmp)
        os.remove(tmp)
        await msg.reply_text("✅ بازگردانی شد!", reply_markup=build_reply_kb(LAYOUT_MAIN))
    except Exception as e:
        if os.path.exists(tmp): os.remove(tmp)
        await msg.reply_text(f"❌ خطا: {e}")
    return ConversationHandler.END

async def cancel_state(update: Update, ctx):
    ctx.user_data.clear()
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ لغو شد.")
    elif update.message:
        await update.message.reply_text("❌ لغو شد.", reply_markup=build_reply_kb(LAYOUT_MAIN))
    return ConversationHandler.END


# ── MAIN ENGINE ──

def main():
    if not TOKEN:
        logger.error("❌ BOT_TOKEN missing!")
        return

    app = Application.builder().token(TOKEN).build()

    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_cb, pattern="^adm_|^ebtn_|^hbtn_")],
        states={
            UPLOAD_CAT: [CallbackQueryHandler(ucat_select, pattern="^ucat_")],
            UPLOAD_FILE: [MessageHandler(filters.Document.ALL | filters.PHOTO, upload_file_receive)],
            UPLOAD_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_note_receive)],
            MANAGE_CAT: [CallbackQueryHandler(admin_cb, pattern="^mcat_")],
            RESTORE_DB: [MessageHandler(filters.Document.ALL, restore_db_receive)],
            SET_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_contact_receive)],
            BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_receive)],
            EDIT_BTN: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_btn_receive)],
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

    logger.info("🤖 Tavansazeh bot engine started successfully...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
