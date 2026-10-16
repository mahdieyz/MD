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

# Default display names if not set in the database
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

# Mapping internal button IDs to internal database category keys (DO NOT CHANGE)
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

def get_btn(key):
    """Fetches the current custom name of a button from the database."""
    return db.get_setting(key, DEFAULT_BUTTONS[key])

# ── KEYBOARDS ──

def main_menu_kb():
    return ReplyKeyboardMarkup([
        [KeyboardButton(get_btn("btn_magnetar")), KeyboardButton(get_btn("btn_switches_main"))],
        [KeyboardButton(get_btn("btn_industrial")), KeyboardButton(get_btn("btn_facade_main"))],
        [KeyboardButton(get_btn("btn_cable")), KeyboardButton(get_btn("btn_intercom")), KeyboardButton(get_btn("btn_fire"))],
        [KeyboardButton(get_btn("btn_milo")), KeyboardButton(get_btn("btn_meloni"))],
        [KeyboardButton(get_btn("btn_contact"))]
    ], resize_keyboard=True)

def facade_kb():
    return ReplyKeyboardMarkup([
        [KeyboardButton(get_btn("btn_mod_noor")), KeyboardButton(get_btn("btn_shaa")), KeyboardButton(get_btn("btn_anvar"))],
        [KeyboardButton(get_btn("btn_back"))]
    ], resize_keyboard=True)

def switches_kb():
    return ReplyKeyboardMarkup([
        [KeyboardButton(get_btn("btn_smart")), KeyboardButton(get_btn("btn_mech"))],
        [KeyboardButton(get_btn("btn_back"))]
    ], resize_keyboard=True)

def back_only_kb():
    return ReplyKeyboardMarkup([[KeyboardButton(get_btn("btn_back"))]], resize_keyboard=True)

def admin_panel_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 آپلود PDF / کاتالوگ", callback_data="adm_upload")],
        [InlineKeyboardButton("🗑️ مدیریت / حذف کاتالوگ", callback_data="adm_manage_pick"),
         InlineKeyboardButton("📞 اطلاعات تماس", callback_data="adm_contact")],
        [InlineKeyboardButton("✏️ ویرایش نام دکمه‌ها", callback_data="adm_edit_btns")],
        [InlineKeyboardButton("💾 دانلود بکاپ", callback_data="adm_backup"),
         InlineKeyboardButton("📥 بازگردانی بکاپ", callback_data="adm_restore")],
        [InlineKeyboardButton("📢 پیام همگانی", callback_data="adm_broadcast"),
         InlineKeyboardButton("📊 آمار", callback_data="adm_stats")]
    ])

def cat_picker_kb(prefix):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_btn("btn_mod_noor"), callback_data=f"{prefix}mod_noor"),
         InlineKeyboardButton(get_btn("btn_magnetar"), callback_data=f"{prefix}magnetar_line")],
        [InlineKeyboardButton(get_btn("btn_industrial"), callback_data=f"{prefix}industrial"),
         InlineKeyboardButton(get_btn("btn_facade_main"), callback_data=f"{prefix}facade")], # 'facade' unused in db normally, but left for layout
        [InlineKeyboardButton(get_btn("btn_shaa"), callback_data=f"{prefix}shaa"),
         InlineKeyboardButton(get_btn("btn_anvar"), callback_data=f"{prefix}anvar")],
        [InlineKeyboardButton(get_btn("btn_cable"), callback_data=f"{prefix}wire_cable"),
         InlineKeyboardButton(get_btn("btn_intercom"), callback_data=f"{prefix}intercom")],
        [InlineKeyboardButton(get_btn("btn_fire"), callback_data=f"{prefix}fire_alarm"),
         InlineKeyboardButton(get_btn("btn_milo"), callback_data=f"{prefix}milo_socket")],
        [InlineKeyboardButton(get_btn("btn_meloni"), callback_data=f"{prefix}meloni_socket"),
         InlineKeyboardButton(get_btn("btn_smart"), callback_data=f"{prefix}smart_switches")],
        [InlineKeyboardButton(get_btn("btn_mech"), callback_data=f"{prefix}mechanical_switches")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="adm_home")]
    ])

def edit_btn_picker_kb():
    kb = []
    row = []
    for key in DEFAULT_BUTTONS.keys():
        current_name = get_btn(key)
        # limit length for visual layout if needed, but telegram handles it
        row.append(InlineKeyboardButton(current_name[:25], callback_data=f"ebtn_{key}"))
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
    if template:
        welcome = template.replace("{name}", u.first_name or "کاربر")
    else:
        welcome = (f"سلام {u.first_name or 'کاربر'} عزیز! 👋\n"
                   "به ربات توان سازه خوش آمدید.\n"
                   "جهت دریافت لیست قیمت و کاتالوگ، از منوی زیر استفاده کنید:")
    await update.message.reply_text(welcome, reply_markup=main_menu_kb())

async def cancel_cmd(update: Update, ctx):
    ctx.user_data.clear()
    await update.message.reply_text("❌ عملیات لغو شد. منوی اصلی:", reply_markup=main_menu_kb())
    return ConversationHandler.END

# ── MAIN DYNAMIC MESSAGE HANDLER ──

async def handle_message(update: Update, ctx):
    text = update.message.text
    chat_id = update.effective_chat.id

    # 1. Reverse lookup: Which button key matches the text the user sent?
    current_btns = {k: get_btn(k) for k in DEFAULT_BUTTONS}
    matched_key = None
    for k, v in current_btns.items():
        if text == v:
            matched_key = k
            break

    if not matched_key:
        return # Not a recognized menu button

    # 2. Handle Menu Navigation based on the internal matched key
    if matched_key == "btn_back":
        await update.message.reply_text("منوی اصلی 👇", reply_markup=main_menu_kb())
        return

    if matched_key == "btn_facade_main":
        await update.message.reply_text("برند مورد نظر را انتخاب کنید:", reply_markup=facade_kb())
        return

    if matched_key == "btn_switches_main":
        await update.message.reply_text("دسته‌بندی را انتخاب کنید:", reply_markup=switches_kb())
        return

    if matched_key == "btn_contact":
        contact = db.get_setting("contact_text",
            "📞 *ارتباط با واحد فروش توان سازه*\n\n"
            "📲 تلفن: 021-12345678\n"
            "👤 پشتیبانی: @Tavansazeh_Admin")
        await update.message.reply_text(contact, parse_mode="Markdown", reply_markup=main_menu_kb())
        return

    # 3. Handle Catalog Requests
    if matched_key in CAT_KEYS:
        cat_key = CAT_KEYS[matched_key]
        files = db.get_catalogs(cat_key)
        if not files:
            await update.message.reply_text(
                f"📂 هنوز کاتالوگی برای «{text}» ثبت نشده است.\nبه زودی لیست قیمت جدید قرار می‌گیرد.",
                reply_markup=back_only_kb())
            return

        await update.message.reply_text(f"⏳ ارسال فایل‌های «{text}»...")
        sent = 0
        for item in files:
            try:
                if item.get("file_type") == "photo":
                    await ctx.bot.send_photo(chat_id=chat_id, photo=item["file_id"], caption=item.get("note") or None)
                else:
                    await ctx.bot.send_document(chat_id=chat_id, document=item["file_id"], caption=item.get("note") or None)
                sent += 1
            except Exception as e:
                logger.error(f"Send file fail for cat={cat_key}: {e}")

        await update.message.reply_text(
            f"✅ {sent} فایل ارسال شد." if sent else "⚠️ ارسال ناموفق بود.",
            reply_markup=back_only_kb())

# ── ADMIN PANEL ──

async def admin_cmd(update: Update, ctx):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ دسترسی ندارید.")
        return
    await update.message.reply_text("🔧 *پنل مدیریت*\nگزینه مورد نظر:", parse_mode="Markdown", reply_markup=admin_panel_kb())

async def admin_cb(update: Update, ctx):
    q = update.callback_query
    await q.answer()
    data = q.data

    if not is_admin(q.from_user.id):
        await q.edit_message_text("⛔ دسترسی ندارید.")
        return ConversationHandler.END

    if data == "adm_stats":
        s = db.get_stats()
        counts = db.count_catalogs_by_category()
        details = "\n".join(f"  • {k}: {v}" for k, v in counts.items()) or "  (خالی)"
        await q.edit_message_text(
            f"📊 *آمار ربات*\n\n👥 کاربران: {s['total_users']}\n📁 کل فایل‌ها: {s['total_files']}\n\n📦 *توزیع کاتالوگ‌ها:*\n{details}",
            parse_mode="Markdown", reply_markup=admin_panel_kb())
        return ConversationHandler.END

    if data == "adm_backup":
        if not os.path.exists(db.db_name):
            await q.edit_message_text("⚠️ فایل دیتابیس یافت نشد.")
            return ConversationHandler.END
        await q.edit_message_text("⏳ در حال ساخت بکاپ امن...")
        try:
            backup_path = db.db_name + ".backup"
            db.backup_to_file(backup_path)
            with open(backup_path, "rb") as f:
                await ctx.bot.send_document(
                    chat_id=q.message.chat_id, document=f,
                    filename=f"backup_{__import__('datetime').datetime.now():%Y%m%d_%H%M}.db",
                    caption="💾 بکاپ دیتابیس ربات")
            os.remove(backup_path)
            await q.edit_message_text("✅ بکاپ ارسال شد.", reply_markup=admin_panel_kb())
        except Exception as e:
            await q.edit_message_text(f"❌ خطا در بکاپ: {e}")
        return ConversationHandler.END

    if data == "adm_restore":
        await q.edit_message_text("📥 فایل بکاپ (`.db`) را ارسال کنید.\n\n⚠️ دیتابیس فعلی به‌طور خودکار پشتیبان‌گیری می‌شود.", parse_mode="Markdown")
        return RESTORE_DB

    if data == "adm_upload":
        await q.edit_message_text("📂 انتخاب دسته برای افزودن فایل:", reply_markup=cat_picker_kb("ucat_"))
        return UPLOAD_CAT

    if data == "adm_manage_pick":
        await q.edit_message_text("🗂️ انتخاب دسته برای مدیریت:", reply_markup=cat_picker_kb("mcat_"))
        return MANAGE_CAT

    if data == "adm_edit_btns":
        await q.edit_message_text("✏️ روی دکمه‌ای که می‌خواهید نامش را تغییر دهید کلیک کنید:", reply_markup=edit_btn_picker_kb())
        return ConversationHandler.END

    if data.startswith("ebtn_"):
        btn_key = data[5:]
        ctx.user_data["edit_btn_key"] = btn_key
        current_name = get_btn(btn_key)
        await q.edit_message_text(f"✏️ تغییر نام دکمه\n\nنام فعلی: «{current_name}»\n\nلطفاً نام جدید را برای این دکمه ارسال کنید:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="adm_home")]]))
        return EDIT_BTN

    if data.startswith("mcat_"):
        cat_key = data[5:]
        files = db.get_catalogs(cat_key)
        if not files:
            await q.edit_message_text("📂 این دسته خالی است.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="adm_home")]]))
            return ConversationHandler.END
        kb = [[InlineKeyboardButton(f"🗑️ {f.get('file_name', 'فایل')} - {f.get('note', '')[:15]}", callback_data=f"del_{f['id']}")] for f in files]
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="adm_home")])
        await q.edit_message_text("🗑️ روی فایل بزنید تا حذف شود:", reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END

    if data.startswith("del_"):
        cid = int(data[4:])
        db.delete_catalog(cid)
        await q.edit_message_text("✅ فایل حذف شد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="adm_home")]]))
        return ConversationHandler.END

    if data == "adm_contact":
        cur = db.get_setting("contact_text", "(خالی)")
        await q.edit_message_text(f"📝 متن فعلی:\n\n{cur}\n\n──────────\nمتن جدید را ارسال کنید:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="adm_home")]]))
        return SET_CONTACT

    if data == "adm_broadcast":
        await q.edit_message_text("📢 متن پیام همگانی را ارسال کنید:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="adm_home")]]))
        return BROADCAST

    if data == "adm_home":
        await q.edit_message_text("🔧 *پنل مدیریت*", parse_mode="Markdown", reply_markup=admin_panel_kb())
        return ConversationHandler.END

    return ConversationHandler.END

# ── CONVERSATION STATE HANDLERS ──

async def ucat_select(update: Update, ctx):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id): return ConversationHandler.END
    ctx.user_data["upload_cat_key"] = q.data[5:]
    await q.edit_message_text(f"📄 فایل را ارسال کنید (PDF یا عکس):")
    return UPLOAD_FILE

async def upload_file_receive(update: Update, ctx):
    msg = update.message
    if msg.document:
        ctx.user_data["upload_file_id"] = msg.document.file_id
        ctx.user_data["upload_file_name"] = msg.document.file_name or "document.pdf"
        ctx.user_data["upload_file_type"] = "document"
    elif msg.photo:
        ctx.user_data["upload_file_id"] = msg.photo[-1].file_id
        ctx.user_data["upload_file_name"] = "photo.jpg"
        ctx.user_data["upload_file_type"] = "photo"
    else:
        await msg.reply_text("⚠️ لطفاً فایل PDF یا عکس ارسال کنید:")
        return UPLOAD_FILE

    await msg.reply_text("📝 فایل دریافت شد!\nاگر توضیحی دارید (مثلاً قیمت) وارد کنید، یا عدد 0 را بفرستید:")
    return UPLOAD_NOTE

async def upload_note_receive(update: Update, ctx):
    note = update.message.text.strip()
    if note == "0": note = ""
    db.add_catalog_file(
        cat_key=ctx.user_data["upload_cat_key"],
        title=ctx.user_data["upload_cat_key"],
        file_id=ctx.user_data["upload_file_id"],
        file_name=ctx.user_data["upload_file_name"],
        note=note,
        file_type=ctx.user_data["upload_file_type"])
    await update.message.reply_text("✅ فایل با موفقیت ذخیره شد!", reply_markup=main_menu_kb())
    ctx.user_data.clear()
    return ConversationHandler.END

async def edit_btn_receive(update: Update, ctx):
    new_text = update.message.text.strip()
    key = ctx.user_data.get("edit_btn_key")
    if key:
        db.set_setting(key, new_text)
        await update.message.reply_text(f"✅ نام دکمه با موفقیت به «{new_text}» تغییر یافت.", reply_markup=main_menu_kb())
    ctx.user_data.clear()
    return ConversationHandler.END

async def restore_db_receive(update: Update, ctx):
    msg = update.message
    if not msg.document or not (msg.document.file_name or "").endswith(".db"):
        await msg.reply_text("⚠️ فایل را به صورت Document با پسوند .db ارسال کنید:")
        return RESTORE_DB

    await msg.reply_text("⏳ دانلود و اعتبارسنجی فایل...")
    tmp_path = "restore_tmp.db"
    try:
        file = await ctx.bot.get_file(msg.document.file_id)
        await file.download_to_drive(custom_path=tmp_path)
        if not db.restore_from_file(tmp_path): raise ValueError("فایل نامعتبر")
        os.remove(tmp_path)
        await msg.reply_text("✅ دیتابیس بازگردانی شد!", reply_markup=main_menu_kb())
    except Exception as e:
        if os.path.exists(tmp_path): os.remove(tmp_path)
        await msg.reply_text(f"❌ بازگردانی ناموفق: {e}")
    return ConversationHandler.END

async def set_contact_receive(update: Update, ctx):
    db.set_setting("contact_text", update.message.text)
    await update.message.reply_text("✅ متن تماس بروزرسانی شد.", reply_markup=main_menu_kb())
    ctx.user_data.clear()
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
        except:
            fail += 1
    await status.edit_text(f"✅ گزارش ارسال:\n├ موفق: {ok}\n└ ناموفق: {fail}")
    await update.message.reply_text("عملیات پایان یافت.", reply_markup=main_menu_kb())
    ctx.user_data.clear()
    return ConversationHandler.END

async def cancel_state(update: Update, ctx):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ لغو شد.")
    elif update.message:
        await update.message.reply_text("❌ لغو شد.", reply_markup=main_menu_kb())
    ctx.user_data.clear()
    return ConversationHandler.END

# ── MAIN ──

def main():
    if not TOKEN:
        logger.error("❌ BOT_TOKEN missing!")
        return

    app = Application.builder().token(TOKEN).build()

    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_cb, pattern="^adm_|^ebtn_")],
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
            CallbackQueryHandler(admin_cb, pattern="^adm_home$")
        ],
        per_message=False,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(admin_conv)
    
    # Listen to any text to check against our dynamic buttons
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🤖 Tavansazeh bot is live with dynamic buttons...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
