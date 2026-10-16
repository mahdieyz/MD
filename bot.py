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

UPLOAD_CAT, UPLOAD_FILE, UPLOAD_NOTE, SET_CONTACT, BROADCAST, RESTORE_DB, MANAGE_CAT = range(7)

def is_admin(uid):
    return uid in ADMIN_IDS

# ── KEYBOARDS ──

CATEGORY_MAP = {
    "test": "mod_noor",
    "مگنتار و چراغ لاینی": "magnetar_line",
    "صنعتی ساختمانی": "industrial",
    "سیم و کابل": "wire_cable",
    "آیفون": "intercom",
    "اعلان حریق": "fire_alarm",
    "پریز کابینتی میلو": "milo_socket",
    "پریز کابینتی ملونی": "meloni_socket",
    "شعاع": "shaa",
    "انوار": "anvar",
    "پریز و کلید هوشمند": "smart_switches",
    "کلید مکانیکی": "mechanical_switches",
}

BACK_BTN = "بازگشت به منوی اصلی"

def main_menu_kb():
    return ReplyKeyboardMarkup([
        [KeyboardButton("مگنتار و چراغ لاینی"), KeyboardButton("کلید ، پریز هوشمند و مکانیکی")],
        [KeyboardButton("صنعتی ساختمانی"), KeyboardButton("نمای ساختمان - محوطه - استخری")],
        [KeyboardButton("سیم و کابل"), KeyboardButton("آیفون"), KeyboardButton("اعلان حریق")],
        [KeyboardButton("پریز کابینتی میلو"), KeyboardButton("پریز کابینتی ملونی")],
        [KeyboardButton("🛒 ثبت سفارش / تماس با ما")]
    ], resize_keyboard=True)

def facade_kb():
    return ReplyKeyboardMarkup([
        [KeyboardButton("مد نور"), KeyboardButton("شعاع"), KeyboardButton("انوار")],
        [KeyboardButton(BACK_BTN)]
    ], resize_keyboard=True)

def switches_kb():
    return ReplyKeyboardMarkup([
        [KeyboardButton("پریز و کلید هوشمند"), KeyboardButton("کلید مکانیکی")],
        [KeyboardButton(BACK_BTN)]
    ], resize_keyboard=True)

def back_only_kb():
    return ReplyKeyboardMarkup([[KeyboardButton(BACK_BTN)]], resize_keyboard=True)

# FIX #4: Only match real button texts (so notes aren't swallowed)
ALL_BUTTONS = set(CATEGORY_MAP.keys()) | {
    BACK_BTN, "منوی اصلی",
    "نمای ساختمان - محوطه - استخری",
    "کلید ، پریز هوشمند و مکانیکی",
    "🛒 ثبت سفارش / تماس با ما",
}
BUTTON_REGEX = "^(" + "|".join(re.escape(b) for b in ALL_BUTTONS) + ")$"

# ── BASIC COMMANDS ──

async def start(update: Update, ctx):
    u = update.effective_user
    db.add_user(u.id, u.username, u.first_name, u.last_name)
    # FIX #3: Correct {name} substitution
    template = db.get_setting("welcome_text")
    if template:
        welcome = template.replace("{name}", u.first_name or "کاربر")
    else:
        welcome = (f"سلام {u.first_name or 'کاربر'} عزیز! 👋\n"
                   "به ربات توان سازه خوش آمدید.\n"
                   "جهت دریافت لیست قیمت و کاتالوگ، از منوی زیر استفاده کنید:")
    await update.message.reply_text(welcome, reply_markup=main_menu_kb())

async def cancel_cmd(update: Update, ctx):
    # FIX #5: Works from both message and callback contexts
    ctx.user_data.clear()
    await update.message.reply_text("❌ لغو شد. از منوی اصلی انتخاب کنید:", reply_markup=main_menu_kb())
    return ConversationHandler.END

# ── MAIN MESSAGE HANDLER ──

async def handle_message(update: Update, ctx):
    text = update.message.text
    chat_id = update.effective_chat.id

    if text in (BACK_BTN, "منوی اصلی"):
        await update.message.reply_text("منوی اصلی 👇", reply_markup=main_menu_kb())
        return

    if text == "نمای ساختمان - محوطه - استخری":
        await update.message.reply_text("برند مورد نظر را انتخاب کنید:", reply_markup=facade_kb())
        return

    if text == "کلید ، پریز هوشمند و مکانیکی":
        await update.message.reply_text("دسته‌بندی را انتخاب کنید:", reply_markup=switches_kb())
        return

    if text == "🛒 ثبت سفارش / تماس با ما":
        contact = db.get_setting("contact_text",
            "📞 *ارتباط با واحد فروش توان سازه*\n\n"
            "📲 تلفن: 021-12345678\n"
            "👤 پشتیبانی: @Tavansazeh_Admin")
        await update.message.reply_text(contact, parse_mode="Markdown", reply_markup=main_menu_kb())
        return

    if text in CATEGORY_MAP:
        cat_key = CATEGORY_MAP[text]
        files = db.get_catalogs(cat_key)
        if not files:
            await update.message.reply_text(
                f"📂 هنوز کاتالوگی برای «{text}» ثبت نشده است.\n"
                "به زودی لیست قیمت جدید قرار می‌گیرد.",
                reply_markup=back_only_kb())
            return

        await update.message.reply_text(f"⏳ ارسال کاتالوگ «{text}»...")
        sent = 0
        for item in files:
            try:
                if item.get("file_type") == "photo":
                    await ctx.bot.send_photo(
                        chat_id=chat_id,
                        photo=item["file_id"],
                        caption=item["note"] or None)
                else:
                    await ctx.bot.send_document(
                        chat_id=chat_id,
                        document=item["file_id"],
                        caption=item["note"] or None)
                sent += 1
            except Exception as e:
                logger.error(f"Send file fail for cat={cat_key}: {e}")

        await update.message.reply_text(
            f"✅ {sent} فایل ارسال شد." if sent else "⚠️ ارسال ناموفق بود.",
            reply_markup=back_only_kb())
        return

# ── ADMIN PANEL ──

def admin_panel_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 آپلود PDF / کاتالوگ", callback_data="adm_upload")],
        [InlineKeyboardButton("🗑️ مدیریت / حذف کاتالوگ", callback_data="adm_manage_pick"),
         InlineKeyboardButton("📞 اطلاعات تماس", callback_data="adm_contact")],
        [InlineKeyboardButton("💾 دانلود بکاپ", callback_data="adm_backup"),
         InlineKeyboardButton("📥 بازگردانی بکاپ", callback_data="adm_restore")],
        [InlineKeyboardButton("📢 پیام همگانی", callback_data="adm_broadcast"),
         InlineKeyboardButton("📊 آمار", callback_data="adm_stats")]
    ])

def cat_picker_kb(prefix):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("مد نور", callback_data=f"{prefix}mod_noor"),
         InlineKeyboardButton("مگنتار/لاینی", callback_data=f"{prefix}magnetar_line")],
        [InlineKeyboardButton("صنعتی ساختمانی", callback_data=f"{prefix}industrial"),
         InlineKeyboardButton("نمای ساختمان", callback_data=f"{prefix}facade")],
        [InlineKeyboardButton("شعاع", callback_data=f"{prefix}shaa"),
         InlineKeyboardButton("انوار", callback_data=f"{prefix}anvar")],
        [InlineKeyboardButton("سیم و کابل", callback_data=f"{prefix}wire_cable"),
         InlineKeyboardButton("آیفون", callback_data=f"{prefix}intercom")],
        [InlineKeyboardButton("اعلان حریق", callback_data=f"{prefix}fire_alarm"),
         InlineKeyboardButton("پریز میلو", callback_data=f"{prefix}milo_socket")],
        [InlineKeyboardButton("پریز ملونی", callback_data=f"{prefix}meloni_socket"),
         InlineKeyboardButton("کلید هوشمند", callback_data=f"{prefix}smart_switches")],
        [InlineKeyboardButton("کلید مکانیکی", callback_data=f"{prefix}mechanical_switches")],
    ])

async def admin_cmd(update: Update, ctx):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ دسترسی ندارید.")
        return
    await update.message.reply_text(
        "🔧 *پنل مدیریت*\nگزینه مورد نظر:",
        parse_mode="Markdown", reply_markup=admin_panel_kb())

async def admin_cb(update: Update, ctx):
    q = update.callback_query
    await q.answer()
    data = q.data

    if not is_admin(q.from_user.id):
        await q.edit_message_text("⛔ دسترسی ندارید.")
        return ConversationHandler.END

    # ── STATS (FIX #8: always return END) ──
    if data == "adm_stats":
        s = db.get_stats()
        counts = db.count_catalogs_by_category()
        details = "\n".join(f"  • {k}: {v}" for k, v in counts.items()) or "  (خالی)"
        await q.edit_message_text(
            f"📊 *آمار ربات*\n\n"
            f"👥 کاربران: {s['total_users']}\n"
            f"📁 کل فایل‌ها: {s['total_files']}\n\n"
            f"📦 *توزیع کاتالوگ‌ها:*\n{details}",
            parse_mode="Markdown", reply_markup=admin_panel_kb())
        return ConversationHandler.END

    # ── BACKUP ──
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
                    chat_id=q.message.chat_id,
                    document=f,
                    filename=f"backup_{__import__('datetime').datetime.now():%Y%m%d_%H%M}.db",
                    caption="💾 بکاپ دیتابیس ربات (شامل کاتالوگ، کاربران و تنظیمات)")
            os.remove(backup_path)
            await q.edit_message_text("✅ بکاپ ارسال شد.", reply_markup=admin_panel_kb())
        except Exception as e:
            logger.error(f"Backup error: {e}")
            await q.edit_message_text(f"❌ خطا در بکاپ: {e}")
        return ConversationHandler.END

    # ── RESTORE ──
    if data == "adm_restore":
        await q.edit_message_text(
            "📥 فایل بکاپ (`.db`) را ارسال کنید.\n\n"
            "⚠️ دیتابیس فعلی به‌طور خودکار پشتیبان‌گیری می‌شود.",
            parse_mode="Markdown")
        return RESTORE_DB

    # ── UPLOAD ──
    if data == "adm_upload":
        await q.edit_message_text("📂 انتخاب دسته برای افزودن فایل:", reply_markup=cat_picker_kb("ucat_"))
        return UPLOAD_CAT

    # ── MANAGE / DELETE ──
    if data == "adm_manage_pick":
        await q.edit_message_text("🗂️ انتخاب دسته برای مدیریت:", reply_markup=cat_picker_kb("mcat_"))
        return MANAGE_CAT

    if data.startswith("mcat_"):
        cat_key = data[5:]
        files = db.get_catalogs(cat_key)
        if not files:
            await q.edit_message_text(
                "📂 این دسته خالی است.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 بازگشت", callback_data="adm_home")]]))
            return ConversationHandler.END
        kb = [
            [InlineKeyboardButton(
                f"🗑️ {f['file_name'] or 'فایل #'+str(f['id'])}",
                callback_data=f"del_{f['id']}")]
            for f in files
        ]
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="adm_home")])
        await q.edit_message_text("🗑️ روی فایل بزنید تا حذف شود:", reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END

    if data.startswith("del_"):
        cid = int(data[4:])
        item = db.get_catalog_by_id(cid)
        db.delete_catalog(cid)
        await q.edit_message_text(
            f"✅ حذف شد: {item['file_name'] if item else cid}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="adm_home")]]))
        return ConversationHandler.END

    # ── CONTACT ──
    if data == "adm_contact":
        cur = db.get_setting("contact_text", "(خالی)")
        await q.edit_message_text(
            f"📝 متن فعلی:\n\n{cur}\n\n──────────\n"
            "متن جدید را ارسال کنید:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ انصراف", callback_data="adm_home")]]))
        return SET_CONTACT

    # ── BROADCAST ──
    if data == "adm_broadcast":
        await q.edit_message_text(
            "📢 متن پیام همگانی را ارسال کنید:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ انصراف", callback_data="adm_home")]]))
        return BROADCAST

    # ── HOME ──
    if data == "adm_home":
        await q.edit_message_text("🔧 *پنل مدیریت*", parse_mode="Markdown",
                                  reply_markup=admin_panel_kb())
        return ConversationHandler.END

    return ConversationHandler.END

# ── CONVERSATION STATE HANDLERS ──

async def ucat_select(update: Update, ctx):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return ConversationHandler.END
    cat_key = q.data[5:]
    ctx.user_data["upload_cat_key"] = cat_key
    await q.edit_message_text(f"📄 فایل را ارسال کنید (PDF یا عکس):")
    return UPLOAD_FILE

# FIX #7: Support both documents AND photos
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

    await msg.reply_text(
        "📝 فایل دریافت شد!\n\n"
        "اگر توضیحی دارید (مثلاً: «لیست بعلاوه ۲۰ درصد می‌باشد») وارد کنید،\n"
        "یا عدد `0` را بفرستید:")
    return UPLOAD_NOTE

async def upload_note_receive(update: Update, ctx):
    note = update.message.text.strip()
    if note == "0":
        note = ""
    db.add_catalog_file(
        cat_key=ctx.user_data["upload_cat_key"],
        title=ctx.user_data["upload_cat_key"],
        file_id=ctx.user_data["upload_file_id"],
        file_name=ctx.user_data["upload_file_name"],
        note=note,
        file_type=ctx.user_data["upload_file_type"])
    await update.message.reply_text(
        "✅ فایل با موفقیت ذخیره و به دکمه متصل شد!",
        reply_markup=main_menu_kb())
    ctx.user_data.clear()
    return ConversationHandler.END

async def restore_db_receive(update: Update, ctx):
    msg = update.message
    if not msg.document:
        await msg.reply_text("⚠️ فایل را به صورت Document ارسال کنید:")
        return RESTORE_DB
    if not (msg.document.file_name or "").endswith(".db"):
        await msg.reply_text("⚠️ فایل باید با پسوند `.db` باشد.")
        return RESTORE_DB

    await msg.reply_text("⏳ دانلود و اعتبارسنجی فایل...")
    tmp_path = "restore_tmp.db"
    try:
        file = await ctx.bot.get_file(msg.document.file_id)
        await file.download_to_drive(custom_path=tmp_path)
        if not db.restore_from_file(tmp_path):
            raise ValueError("فایل دیتابیس معتبر نیست")
        os.remove(tmp_path)
        await msg.reply_text(
            "✅ دیتابیس با موفقیت بازگردانی شد!",
            reply_markup=main_menu_kb())
    except Exception as e:
        logger.error(f"Restore fail: {e}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
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
    await update.message.reply_text(f"⏳ ارسال به {len(users)} کاربر...")
    ok = fail = 0
    for u in users:
        try:
            await ctx.bot.send_message(u["user_id"], msg[:4000])
            ok += 1
        except Exception:
            fail += 1
    await update.message.reply_text(
        f"✅ گزارش ارسال:\n├ موفق: {ok}\n└ ناموفق: {fail}",
        reply_markup=main_menu_kb())
    ctx.user_data.clear()
    return ConversationHandler.END

async def cancel_state(update: Update, ctx):
    """Fallback cancel from callbacks or text."""
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

    # FIX #2: admin_nav lets users escape any state
    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_cb, pattern="^adm_")],
        states={
            UPLOAD_CAT: [
                CallbackQueryHandler(ucat_select, pattern="^ucat_"),
                CallbackQueryHandler(admin_cb, pattern="^adm_"),
            ],
            UPLOAD_FILE: [
                MessageHandler(filters.Document.ALL | filters.PHOTO, upload_file_receive),
                CallbackQueryHandler(admin_cb, pattern="^adm_"),
                CommandHandler("cancel", cancel_state),
            ],
            UPLOAD_NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, upload_note_receive),
                CommandHandler("cancel", cancel_state),
            ],
            MANAGE_CAT: [
                CallbackQueryHandler(admin_cb, pattern="^mcat_|^adm_"),
            ],
            RESTORE_DB: [
                MessageHandler(filters.Document.ALL, restore_db_receive),
                CallbackQueryHandler(admin_cb, pattern="^adm_"),
                CommandHandler("cancel", cancel_state),
            ],
            SET_CONTACT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_contact_receive),
                CallbackQueryHandler(admin_cb, pattern="^adm_"),
                CommandHandler("cancel", cancel_state),
            ],
            BROADCAST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_receive),
                CallbackQueryHandler(admin_cb, pattern="^adm_"),
                CommandHandler("cancel", cancel_state),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_state),
            CommandHandler("start", start),
        ],
        per_message=False,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(admin_conv)
    # FIX #4: only match real button texts
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex(BUTTON_REGEX),
        handle_message))

    logger.info("🤖 Tavansazeh bot is live...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
