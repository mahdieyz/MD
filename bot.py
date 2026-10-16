import os
import re
import logging
import asyncio
import tempfile
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)
from database import Database

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

db = Database()

ADMIN_IDS = [int(x.strip()) for x in os.environ.get('ADMIN_IDS', '').split(',') if x.strip()]

# ─── Menu Structure ───
MAIN_MENU = [
    ["مگنتار و چراغ لاینی"],
    ["کلید ، پریز هوشمند و مکانیکی"],
    ["صنعتی ساختمانی"],
    ["نمای ساختمان - محوطه - استخری"],
    ["سیم و کابل"],
    ["آیفون"],
    ["اعلان حریق"],
    ["پریز کابینتی میلو"],
    ["پریز کابینتی ملونی"],
    ["🛒 ثبت سفارش / تماس با ما"]
]

SUB_MENUS = {
    "نمای ساختمان - محوطه - استخری": [
        ["مد نور"], ["شعاع"], ["انوار"], ["🔙 بازگشت"]
    ],
    "کلید ، پریز هوشمند و مکانیکی": [
        ["هوشمند"], ["مکانیکی"], ["🔙 بازگشت"]
    ]
}

ALL_BUTTONS = set()
for row in MAIN_MENU:
    ALL_BUTTONS.update(row)
for sub in SUB_MENUS.values():
    for row in sub:
        ALL_BUTTONS.update(row)

BUTTON_REGEX = re.compile('^(' + '|'.join(re.escape(b) for b in ALL_BUTTONS) + ')$')

# Admin states
(ADMIN_MENU, UPLOAD_CATEGORY, UPLOAD_FILE, UPLOAD_NOTE,
 DELETE_SELECT_CAT, DELETE_SELECT_ITEM,
 EDIT_CONTACT, BROADCAST_MSG, RESTORE_DB) = range(9)

ADMIN_KEYBOARD = [
    ["📤 آپلود PDF / کاتالوگ"],
    ["🗑️ مدیریت / حذف کاتالوگ"],
    ["📞 اطلاعات تماس"],
    ["📢 پیام همگانی"],
    ["📊 آمار"],
    ["💾 دانلود بکاپ"],
    ["📥 بازگردانی بکاپ"],
    ["❌ خروج از پنل"]
]


def is_admin(user_id):
    return user_id in ADMIN_IDS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.register_user(user.id, user.username, user.first_name, user.last_name)
    keyboard = ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
    await update.message.reply_text(
        f"سلام {user.first_name} 👋\nبه ربات کاتالوگ توان سازه خوش آمدید.\nلطفاً یک دسته‌بندی را انتخاب کنید:",
        reply_markup=keyboard
    )


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    db.register_user(user.id, user.username, user.first_name, user.last_name)

    if text == "🔙 بازگشت":
        keyboard = ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
        await update.message.reply_text("دسته‌بندی اصلی:", reply_markup=keyboard)
        return

    if text == "🛒 ثبت سفارش / تماس با ما":
        contact_text = db.get_setting('contact_text',
            "📞 برای ثبت سفارش با ما تماس بگیرید:\n\n"
            "📱 شماره تماس: 09123456789\n"
            "📧 ایمیل: info@tavansazeh.com\n"
            "🌐 وبسایت: www.tavansazeh.com"
        )
        await update.message.reply_text(contact_text)
        return

    if text in SUB_MENUS:
        keyboard = ReplyKeyboardMarkup(SUB_MENUS[text], resize_keyboard=True)
        await update.message.reply_text(f"📂 {text}\nزیردسته را انتخاب کنید:", reply_markup=keyboard)
        return

    catalogs = db.get_catalogs(text)
    if catalogs:
        for cat in catalogs:
            caption_parts = []
            if cat['caption']:
                caption_parts.append(cat['caption'])
            if cat['custom_note']:
                caption_parts.append(f"\n📌 {cat['custom_note']}")
            caption = '\n'.join(caption_parts) if caption_parts else None

            try:
                if cat['file_type'] == 'photo':
                    await update.message.reply_photo(photo=cat['file_id'], caption=caption)
                else:
                    await update.message.reply_document(document=cat['file_id'], caption=caption)
            except Exception as e:
                logger.error(f"Error sending catalog {cat['id']}: {e}")
                await update.message.reply_text(f"⚠️ خطا در ارسال فایل #{cat['id']}")
    else:
        await update.message.reply_text(f"📂 {text}\n\nفایلی در این دسته‌بندی موجود نیست.")


# ─── Admin Conversation ───
async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ شما دسترسی ادمین ندارید.")
        return ConversationHandler.END
    keyboard = ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True)
    await update.message.reply_text("🔧 پنل مدیریت:", reply_markup=keyboard)
    return ADMIN_MENU


async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "❌ خروج از پنل":
        keyboard = ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
        await update.message.reply_text("از پنل خارج شدید.", reply_markup=keyboard)
        return ConversationHandler.END

    if text == "📤 آپلود PDF / کاتالوگ":
        cats = [row[0] for row in MAIN_MENU if row[0] != "🛒 ثبت سفارش / تماس با ما"]
        for sub_items in SUB_MENUS.values():
            for row in sub_items:
                if row[0] != "🔙 بازگشت" and row[0] not in cats:
                    cats.append(row[0])
        kb = [[c] for c in cats] + [["❌ انصراف"]]
        keyboard = ReplyKeyboardMarkup(kb, resize_keyboard=True)
        await update.message.reply_text("دسته‌بندی مقصد را انتخاب کنید:", reply_markup=keyboard)
        return UPLOAD_CATEGORY

    if text == "🗑️ مدیریت / حذف کاتالوگ":
        cats = db.get_all_categories()
        if not cats:
            await update.message.reply_text("هیچ فایلی موجود نیست.")
            return ADMIN_MENU
        kb = [[c] for c in cats] + [["❌ انصراف"]]
        keyboard = ReplyKeyboardMarkup(kb, resize_keyboard=True)
        await update.message.reply_text("دسته‌بندی را انتخاب کنید:", reply_markup=keyboard)
        return DELETE_SELECT_CAT

    if text == "📞 اطلاعات تماس":
        current = db.get_setting('contact_text', 'تنظیم نشده')
        await update.message.reply_text(f"متن فعلی:\n\n{current}\n\nمتن جدید را ارسال کنید یا /cancel بزنید:")
        return EDIT_CONTACT

    if text == "📢 پیام همگانی":
        await update.message.reply_text("متن پیام همگانی را ارسال کنید یا /cancel بزنید:")
        return BROADCAST_MSG

    if text == "📊 آمار":
        total_users = db.get_user_count()
        active_users = db.get_active_user_count()
        total_files = db.get_catalog_count()
        cat_stats = db.get_category_stats()
        broadcasts = db.get_broadcast_logs(5)

        stats = f"""📊 آمار ربات:

👥 کل کاربران: {total_users}
✅ کاربران فعال: {active_users}
🚫 کاربران بلاک‌شده: {total_users - active_users}
📁 کل فایل‌ها: {total_files}

📂 فایل‌ها به تفکیک:
"""
        for cs in cat_stats:
            stats += f"  • {cs['category']}: {cs['cnt']}\n"

        if broadcasts:
            stats += "\n📢 آخرین پیام‌های همگانی:\n"
            for b in broadcasts:
                stats += f"  • {b['sent_at'][:16]} — ✅{b['sent_count']} ❌{b['fail_count']}\n"

        await update.message.reply_text(stats)
        return ADMIN_MENU

    if text == "💾 دانلود بکاپ":
        try:
            backup_path = f"/tmp/backup_{int(__import__('time').time())}.db"
            db.backup_to_file(backup_path)
            with open(backup_path, 'rb') as f:
                await update.message.reply_document(document=f, filename="bot_backup.db", caption="✅ بکاپ دیتابیس")
            os.remove(backup_path)
        except Exception as e:
            await update.message.reply_text(f"⚠️ خطا: {e}")
        return ADMIN_MENU

    if text == "📥 بازگردانی بکاپ":
        await update.message.reply_text("فایل .db بکاپ را ارسال کنید یا /cancel بزنید:")
        return RESTORE_DB

    await update.message.reply_text("گزینه نامعتبر.")
    return ADMIN_MENU


async def upload_category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ انصراف":
        keyboard = ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True)
        await update.message.reply_text("لغو شد.", reply_markup=keyboard)
        return ADMIN_MENU
    context.user_data['upload_category'] = text
    await update.message.reply_text(
        f"📂 دسته: {text}\n\nحالا فایل PDF یا عکس را ارسال کنید:",
        reply_markup=ReplyKeyboardMarkup([["❌ انصراف"]], resize_keyboard=True)
    )
    return UPLOAD_FILE


async def upload_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.text == "❌ انصراف":
        keyboard = ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True)
        await msg.reply_text("لغو شد.", reply_markup=keyboard)
        return ADMIN_MENU

    if msg.document:
        context.user_data['file_id'] = msg.document.file_id
        context.user_data['file_type'] = 'document'
        context.user_data['original_filename'] = msg.document.file_name
        context.user_data['caption'] = msg.caption or ''
    elif msg.photo:
        context.user_data['file_id'] = msg.photo[-1].file_id
        context.user_data['file_type'] = 'photo'
        context.user_data['original_filename'] = None
        context.user_data['caption'] = msg.caption or ''
    else:
        await msg.reply_text("لطفاً فایل PDF یا عکس ارسال کنید.")
        return UPLOAD_FILE

    await msg.reply_text("یادداشت قیمت (مثلاً 'لیست بعلاوه ۲۰ درصد') را بنویسید.\n/skip برای رد کردن:")
    return UPLOAD_NOTE


async def upload_note_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    note = None if text == '/skip' else text

    catalog_id = db.add_catalog(
        category=context.user_data['upload_category'],
        file_id=context.user_data['file_id'],
        file_type=context.user_data['file_type'],
        caption=context.user_data.get('caption'),
        custom_note=note,
        uploaded_by=update.effective_user.id,
        original_filename=context.user_data.get('original_filename')
    )

    keyboard = ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True)
    await update.message.reply_text(f"✅ فایل #{catalog_id} در «{context.user_data['upload_category']}» ذخیره شد.", reply_markup=keyboard)
    context.user_data.clear()
    return ADMIN_MENU


async def delete_cat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ انصراف":
        keyboard = ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True)
        await update.message.reply_text("لغو شد.", reply_markup=keyboard)
        return ADMIN_MENU

    catalogs = db.get_catalogs(text)
    if not catalogs:
        await update.message.reply_text("فایلی یافت نشد.")
        return ADMIN_MENU

    context.user_data['delete_category'] = text
    msg = f"📂 {text}:\n\n"
    for c in catalogs:
        fname = c['original_filename'] or c['file_type']
        msg += f"🔹 #{c['id']} — {fname}"
        if c['custom_note']:
            msg += f" — {c['custom_note']}"
        msg += "\n"
    msg += "\nشماره فایل برای حذف را ارسال کنید یا /cancel بزنید:"
    await update.message.reply_text(msg)
    return DELETE_SELECT_ITEM


async def delete_item_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == '/cancel':
        keyboard = ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True)
        await update.message.reply_text("لغو شد.", reply_markup=keyboard)
        return ADMIN_MENU

    try:
        catalog_id = int(text)
        cat = db.get_catalog_by_id(catalog_id)
        if cat:
            db.delete_catalog(catalog_id)
            await update.message.reply_text(f"✅ فایل #{catalog_id} حذف شد.")
        else:
            await update.message.reply_text("فایل یافت نشد.")
    except ValueError:
        await update.message.reply_text("لطفاً عدد وارد کنید.")
        return DELETE_SELECT_ITEM

    keyboard = ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True)
    await update.message.reply_text("پنل مدیریت:", reply_markup=keyboard)
    return ADMIN_MENU


async def edit_contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == '/cancel':
        keyboard = ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True)
        await update.message.reply_text("لغو شد.", reply_markup=keyboard)
        return ADMIN_MENU
    db.set_setting('contact_text', text)
    keyboard = ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True)
    await update.message.reply_text("✅ اطلاعات تماس بروزرسانی شد.", reply_markup=keyboard)
    return ADMIN_MENU


async def broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == '/cancel':
        keyboard = ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True)
        await update.message.reply_text("لغو شد.", reply_markup=keyboard)
        return ADMIN_MENU

    user_ids = db.get_active_user_ids()
    sent = 0
    failed = 0
    status_msg = await update.message.reply_text(f"📢 در حال ارسال به {len(user_ids)} کاربر...")

    for uid in user_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=text)
            sent += 1
        except Exception:
            failed += 1
        if (sent + failed) % 25 == 0:
            try:
                await status_msg.edit_text(f"📢 ارسال... {sent + failed}/{len(user_ids)}")
            except Exception:
                pass
        await asyncio.sleep(0.05)

    db.log_broadcast(text, sent, failed, update.effective_user.id)
    keyboard = ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True)
    await status_msg.edit_text(f"✅ ارسال تمام شد.\n✅ موفق: {sent}\n❌ ناموفق: {failed}")
    await update.message.reply_text("پنل مدیریت:", reply_markup=keyboard)
    return ADMIN_MENU


async def restore_db_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.text == '/cancel':
        keyboard = ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True)
        await msg.reply_text("لغو شد.", reply_markup=keyboard)
        return ADMIN_MENU

    if not msg.document:
        await msg.reply_text("لطفاً فایل .db ارسال کنید.")
        return RESTORE_DB

    try:
        file = await context.bot.get_file(msg.document.file_id)
        tmp_path = f"/tmp/restore_{int(__import__('time').time())}.db"
        await file.download_to_drive(tmp_path)
        db.restore_from_file(tmp_path)
        os.remove(tmp_path)
        keyboard = ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True)
        await msg.reply_text("✅ دیتابیس بازگردانی شد.", reply_markup=keyboard)
    except Exception as e:
        await msg.reply_text(f"⚠️ خطا: {e}")
    return ADMIN_MENU


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
    await update.message.reply_text("لغو شد.", reply_markup=keyboard)
    return ConversationHandler.END


def create_bot_app():
    token = os.environ['BOT_TOKEN']
    app = Application.builder().token(token).build()

    admin_conv = ConversationHandler(
        entry_points=[CommandHandler('admin', admin_start)],
        states={
            ADMIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler)],
            UPLOAD_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_category_handler)],
            UPLOAD_FILE: [
                MessageHandler(filters.Document.ALL | filters.PHOTO, upload_file_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, upload_file_handler)
            ],
            UPLOAD_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_note_handler)],
            DELETE_SELECT_CAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_cat_handler)],
            DELETE_SELECT_ITEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_item_handler)],
            EDIT_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_contact_handler)],
            BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_handler)],
            RESTORE_DB: [
                MessageHandler(filters.Document.ALL, restore_db_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, restore_db_handler)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    app.add_handler(admin_conv)
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.Regex(BUTTON_REGEX), handle_menu))

    return app
