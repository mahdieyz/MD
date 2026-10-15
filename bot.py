import os, logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters
)
from database import Database

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
db = Database()

TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "0").split(",")]

# Admin Conversation States
UPLOAD_CAT, UPLOAD_FILE, UPLOAD_NOTE, SET_CONTACT, BROADCAST = range(5)

def is_admin(uid):
    return uid in ADMIN_IDS

# ── KEYBOARDS (Matching Screenshot Exactly) ──

def main_menu_kb():
    keyboard = [
        [KeyboardButton("مگنتار و چراغ لاینی"), KeyboardButton("کلید ، پریز هوشمند و مکانیکی")],
        [KeyboardButton("صنعتی ساختمانی"), KeyboardButton("نمای ساختمان - محوطه - استخری")],
        [KeyboardButton("سیم و کابل"), KeyboardButton("آیفون"), KeyboardButton("اعلان حریق")],
        [KeyboardButton("پریز کابینتی میلو"), KeyboardButton("پریز کابینتی ملونی")],
        [KeyboardButton("🛒 ثبت سفارش / تماس با ما")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def sub_menu_facade_kb():
    keyboard = [
        [KeyboardButton("مد نور"), KeyboardButton("شعاع"), KeyboardButton("انوار")],
        [KeyboardButton("بازگشت به منوی اصلی")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def sub_menu_switches_kb():
    keyboard = [
        [KeyboardButton("پریز و کلید هوشمند"), KeyboardButton("کلید مکانیکی")],
        [KeyboardButton("بازگشت به منوی اصلی")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def back_only_kb():
    return ReplyKeyboardMarkup([[KeyboardButton("بازگشت به منوی اصلی")]], resize_keyboard=True)

# ── HANDLERS ──

async def start(update: Update, ctx):
    u = update.effective_user
    db.add_user(u.id, u.username, u.first_name, u.last_name)
    welcome = db.get_setting("welcome_text", f"سلام {u.first_name} عزیز! 👋\nبه ربات توان سازه خوش آمدید.\nجهت دریافت لیست قیمت و کاتالوگ، از منوی زیر استفاده کنید:")
    await update.message.reply_text(welcome, reply_markup=main_menu_kb())

async def handle_message(update: Update, ctx):
    text = update.message.text
    chat_id = update.effective_chat.id

    # 1. Main Navigation / Categories
    if text == "بازگشت به منوی اصلی" or text == "منوی اصلی":
        await update.message.reply_text("به منوی اصلی بازگشتید 👇", reply_markup=main_menu_kb())

    elif text == "نمای ساختمان - محوطه - استخری":
        await update.message.reply_text("لطفا برند یا دسته مورد نظر را انتخاب کنید:", reply_markup=sub_menu_facade_kb())

    elif text == "کلید ، پریز هوشمند و مکانیکی":
        await update.message.reply_text("دسته‌بندی کلید و پریز را انتخاب کنید:", reply_markup=sub_menu_switches_kb())

    elif text == "🛒 ثبت سفارش / تماس با ما":
        contact = db.get_setting("contact_text", "📞 *ارتباط با واحد فروش توان سازه*\n\n📲 تلفن: 021-12345678\n👤 پشتیبانی تلگرام: @Tavansazeh_Admin")
        await update.message.reply_text(contact, parse_mode="Markdown", reply_markup=main_menu_kb())

    # 2. Product Items (Sends PDFs from Database)
    else:
        # Category Keys Mapping
        category_map = {
            "مد نور": "mod_noor",
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
            "کلید مکانیکی": "mechanical_switches"
        }

        if text in category_map:
            cat_key = category_map[text]
            files = db.get_catalogs(cat_key)

            if not files:
                await update.message.reply_text(
                    f"📂 هنوز کاتالوگی برای '{text}' ثبت نشده است.\n\nبه زودی لیست قیمت جدید قرار خواهد گرفت.",
                    reply_markup=back_only_kb()
                )
                return

            await update.message.reply_text(f"⏳ در حال ارسال کاتالوگ و لیست قیمت {text}...")

            for item in files:
                # Send Document/PDF
                if item["file_id"]:
                    try:
                        await ctx.bot.send_document(
                            chat_id=chat_id,
                            document=item["file_id"],
                            caption=item["note"] if item["note"] else None
                        )
                    except Exception as e:
                        logging.error(f"Error sending file: {e}")

            await update.message.reply_text("✅ تمام فایل‌ها ارسال شدند.", reply_markup=back_only_kb())


# ── ADMIN PANEL FOR MANAGING PDFs ──

async def admin_cmd(update: Update, ctx):
    if not is_admin(update.effective_user.id):
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 آپلود PDF / کاتالوگ جدید", callback_data="adm_upload")],
        [InlineKeyboardButton("🗑️ مدیریت / حذف کاتالوگ‌ها", callback_data="adm_manage")],
        [InlineKeyboardButton("📞 تنظیم اطلاعات تماس", callback_data="adm_contact")],
        [InlineKeyboardButton("💾 دانلود فایل بکاپ (Database)", callback_data="adm_backup")], # ← NEW BUTTON
        [InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="adm_broadcast")],
        [InlineKeyboardButton("📊 آمار کاربران", callback_data="adm_stats")]
    ])
    await update.message.reply_text("🔧 *پنل مدیریت کاتالوگ‌ها*\nگزینه مورد نظر را انتخاب کنید:", parse_mode="Markdown", reply_markup=kb)

async def admin_cb(update: Update, ctx):
    q = update.callback_query; await q.answer()
    data = q.data

    if data == "adm_stats":
        s = db.get_stats()
        await q.edit_message_text(f"📊 *آمار ربات*\n\n👥 کاربران: {s['total_users']}\n📁 کل فایل‌های آپلود شده: {s['total_files']}", parse_mode="Markdown")

    elif data == "adm_upload":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("مد نور", callback_data="cat_mod_noor"), InlineKeyboardButton("مگنتار/لاینی", callback_data="cat_magnetar_line")],
            [InlineKeyboardButton("صنعتی ساختمانی", callback_data="cat_industrial"), InlineKeyboardButton("سیم و کابل", callback_data="cat_wire_cable")],
            [InlineKeyboardButton("آیفون", callback_data="cat_intercom"), InlineKeyboardButton("اعلان حریق", callback_data="cat_fire_alarm")],
            [InlineKeyboardButton("پریز میلو", callback_data="cat_milo_socket"), InlineKeyboardButton("پریز ملونی", callback_data="cat_meloni_socket")],
        ])
        await q.edit_message_text("📂 دسته‌ای که می‌خواهید PDF به آن اضافه شود را انتخاب کنید:", reply_markup=kb)
        return UPLOAD_CAT

    elif data == "adm_contact":
        await q.edit_message_text("📝 متن جدید بخش تماس با ما / ثبت سفارش را ارسال کنید:")
        return SET_CONTACT

    elif data == "adm_broadcast":
        await q.edit_message_text("📢 متن پیام همگانی را ارسال کنید:")
        return BROADCAST

    elif data == "adm_backup":
        if os.path.exists(db.db_name):
            await update.message.reply_text("⏳ در حال آماده‌سازی فایل دیتابیس...")
            await ctx.bot.send_document(
                chat_id=update.effective_chat.id,
                document=open(db.db_name, "rb"),
                filename="bot_database_backup.db",
                caption="💾 *فایل بکاپ دیتابیس ربات*\nشامل کلیه کاتالوگ‌ها، کاربران و تنظیمات."
            )
        else:
          
        await update.message.reply_text("⚠️ فایل دیتابیس یافت نشد.")
        
async def upload_cat_select(update: Update, ctx):
    q = update.callback_query; await q.answer()
    cat_key = q.data.replace("cat_", "")
    ctx.user_data["upload_cat_key"] = cat_key
    await q.edit_message_text(f"📄 حالا فایل PDF یا کاتالوگ مربوطه را ارسال کنید:")
    return UPLOAD_FILE

async def upload_file_receive(update: Update, ctx):
    if update.message.document:
        file_id = update.message.document.file_id
        file_name = update.message.document.file_name
        ctx.user_data["upload_file_id"] = file_id
        ctx.user_data["upload_file_name"] = file_name

        await update.message.reply_text(
            "📝 فایل دریافت شد!\n\nاگر توضیحی یا متنی دارد (مثلا: 'لیست بعلاوه ۲۰ درصد میباشد') وارد کنید، یا عدد 0 را بفرستید:"
        )
        return UPLOAD_NOTE
    else:
        await update.message.reply_text("⚠️ لطفاً فایل را به صورت Document (PDF یا تصویر) ارسال کنید:")
        return UPLOAD_FILE

async def upload_note_receive(update: Update, ctx):
    note = update.message.text
    if note == "0":
        note = ""

    cat_key = ctx.user_data["upload_cat_key"]
    file_id = ctx.user_data["upload_file_id"]
    file_name = ctx.user_data["upload_file_name"]

    db.add_catalog_file(cat_key, cat_key, file_id, file_name, note)

    await update.message.reply_text("✅ فایل با موفقیت ذخیره شد و به دکمه مربوطه متصل گردید!", reply_markup=main_menu_kb())
    return ConversationHandler.END

async def set_contact_receive(update: Update, ctx):
    db.set_setting("contact_text", update.message.text)
    await update.message.reply_text("✅ اطلاعات تماس بروزرسانی شد.", reply_markup=main_menu_kb())
    return ConversationHandler.END

async def broadcast_receive(update: Update, ctx):
    msg = update.message.text
    users = db.get_all_users()
    ok = 0
    for u in users:
        try:
            await ctx.bot.send_message(u["user_id"], msg)
            ok += 1
        except:
            pass
    await update.message.reply_text(f"✅ پیام به {ok} کاربر ارسال شد.", reply_markup=main_menu_kb())
    return ConversationHandler.END

async def cancel(update: Update, ctx):
    await update.message.reply_text("❌ انصراف داده شد.", reply_markup=main_menu_kb())
    return ConversationHandler.END

# ── MAIN ENGINE ──

def main():
    if not TOKEN:
        logging.error("BOT_TOKEN is missing!")
        return

    app = Application.builder().token(TOKEN).build()

    upload_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_cb, pattern="^adm_")],
        states={
            UPLOAD_CAT: [CallbackQueryHandler(upload_cat_select, pattern="^cat_")],
            UPLOAD_FILE: [MessageHandler(filters.Document.ALL | filters.PHOTO, upload_file_receive)],
            UPLOAD_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_note_receive)],
            SET_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_contact_receive)],
            BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_receive)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(upload_conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("🤖 Bot is active...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
