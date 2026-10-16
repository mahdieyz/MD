import os
import re
import logging
import asyncio
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from database import Database

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bot")

db = Database()

def get_admin_ids():
    raw = os.environ.get("ADMIN_IDS", "")
    ids = []
    for x in raw.split(","):
        x = x.strip()
        if x.isdigit():
            ids.append(int(x))
    return ids

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
    ["🛒 ثبت سفارش / تماس با ما"],
]

SUB_MENUS = {
    "نمای ساختمان - محوطه - استخری": [
        ["مد نور"], ["شعاع"], ["انوار"], ["🔙 بازگشت"]
    ],
    "کلید ، پریز هوشمند و مکانیکی": [
        ["هوشمند"], ["مکانیکی"], ["🔙 بازگشت"]
    ],
}

ALL_BUTTONS = set()
for row in MAIN_MENU:
    ALL_BUTTONS.update(row)
for sub in SUB_MENUS.values():
    for row in sub:
        ALL_BUTTONS.update(row)

BUTTON_REGEX = re.compile("^(" + "|".join(re.escape(b) for b in sorted(ALL_BUTTONS, key=len, reverse=True)) + ")$")

(
    ADMIN_MENU, UPLOAD_CATEGORY, UPLOAD_FILE, UPLOAD_NOTE,
    DELETE_SELECT_CAT, DELETE_SELECT_ITEM,
    EDIT_CONTACT, BROADCAST_MSG, RESTORE_DB,
) = range(9)

ADMIN_KEYBOARD = [
    ["📤 آپلود PDF / کاتالوگ"],
    ["🗑️ مدیریت / حذف کاتالوگ"],
    ["📞 اطلاعات تماس"],
    ["📢 پیام همگانی"],
    ["📊 آمار"],
    ["💾 دانلود بکاپ"],
    ["📥 بازگردانی بکاپ"],
    ["❌ خروج از پنل"],
]

def is_admin(user_id: int) -> bool:
    return user_id in get_admin_ids()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.register_user(user.id, user.username, user.first_name, user.last_name)
    welcome = db.get_setting(
        "welcome_text",
        f"سلام {user.first_name or ''} 👋\nبه ربات کاتالوگ توان سازه خوش آمدید.\nلطفاً یک دسته‌بندی را انتخاب کنید:",
    )
    await update.message.reply_text(welcome, reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True))


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    user = update.effective_user
    db.register_user(user.id, user.username, user.first_name, user.last_name)

    if text == "🔙 بازگشت":
        await update.message.reply_text("دسته‌بندی اصلی:", reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True))
        return

    if text == "🛒 ثبت سفارش / تماس با ما":
        contact = db.get_setting(
            "contact_text",
            "📞 برای ثبت سفارش با ما تماس بگیرید:\n\n📱 شماره تماس: 09123456789",
        )
        await update.message.reply_text(contact)
        return

    if text in SUB_MENUS:
        await update.message.reply_text(
            f"📂 {text}\nزیردسته را انتخاب کنید:",
            reply_markup=ReplyKeyboardMarkup(SUB_MENUS[text], resize_keyboard=True),
        )
        return

    catalogs = db.get_catalogs(text)
    if not catalogs:
        await update.message.reply_text(f"📂 {text}\n\nفایلی در این دسته‌بندی موجود نیست.")
        return

    for cat in catalogs:
        parts = []
        if cat["caption"]:
            parts.append(cat["caption"])
        if cat["custom_note"]:
            parts.append(f"📌 {cat['custom_note']}")
        caption = "\n\n".join(parts) if parts else None
        try:
            if cat["file_type"] == "photo":
                await update.message.reply_photo(photo=cat["file_id"], caption=caption)
            else:
                await update.message.reply_document(document=cat["file_id"], caption=caption)
        except Exception as e:
            logger.error("Send catalog %s failed: %s", cat["id"], e)
            await update.message.reply_text(f"⚠️ خطا در ارسال فایل #{cat['id']}")


async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ شما دسترسی ادمین ندارید.")
        return ConversationHandler.END
    await update.message.reply_text(
        "🔧 پنل مدیریت تلگرام:",
        reply_markup=ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True),
    )
    return ADMIN_MENU


async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""

    if text == "❌ خروج از پنل":
        await update.message.reply_text("از پنل خارج شدید.", reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True))
        return ConversationHandler.END

    if text == "📤 آپلود PDF / کاتالوگ":
        cats = [r[0] for r in MAIN_MENU if r[0] not in SUB_MENUS and r[0] != "🛒 ثبت سفارش / تماس با ما"]
        for items in SUB_MENUS.values():
            for row in items:
                if row[0] != "🔙 بازگشت" and row[0] not in cats:
                    cats.append(row[0])
        kb = [[c] for c in cats] + [["❌ انصراف"]]
        await update.message.reply_text("دسته‌بندی مقصد را انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return UPLOAD_CATEGORY

    if text == "🗑️ مدیریت / حذف کاتالوگ":
        cats = db.get_all_categories()
        if not cats:
            await update.message.reply_text("هیچ فایلی موجود نیست.")
            return ADMIN_MENU
        kb = [[c] for c in cats] + [["❌ انصراف"]]
        await update.message.reply_text("دسته‌بندی را انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return DELETE_SELECT_CAT

    if text == "📞 اطلاعات تماس":
        current = db.get_setting("contact_text", "تنظیم نشده")
        await update.message.reply_text(f"متن فعلی:\n\n{current}\n\nمتن جدید را بفرستید یا /cancel")
        return EDIT_CONTACT

    if text == "📢 پیام همگانی":
        await update.message.reply_text("متن پیام همگانی را بفرستید یا /cancel")
        return BROADCAST_MSG

    if text == "📊 آمار":
        total_users = db.get_user_count()
        active_users = db.get_active_user_count()
        total_files = db.get_catalog_count()
        cat_stats = db.get_category_stats()
        lines = [
            "📊 آمار ربات:",
            f"👥 کل کاربران: {total_users}",
            f"✅ فعال: {active_users}",
            f"📁 فایل‌ها: {total_files}",
            "",
            "📂 تفکیک:",
        ]
        for cs in cat_stats:
            lines.append(f"  • {cs['category']}: {cs['cnt']}")
        await update.message.reply_text("\n".join(lines))
        return ADMIN_MENU

    if text == "💾 دانلود بکاپ":
        try:
            path = f"/tmp/backup_{int(__import__('time').time())}.db"
            db.backup_to_file(path)
            with open(path, "rb") as f:
                await update.message.reply_document(document=f, filename="bot_backup.db", caption="✅ بکاپ")
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            await update.message.reply_text(f"⚠️ خطا: {e}")
        return ADMIN_MENU

    if text == "📥 بازگردانی بکاپ":
        await update.message.reply_text("فایل .db را بفرستید یا /cancel")
        return RESTORE_DB

    await update.message.reply_text("گزینه نامعتبر است.")
    return ADMIN_MENU


async def upload_category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    if text == "❌ انصراف":
        await update.message.reply_text("لغو شد.", reply_markup=ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True))
        return ADMIN_MENU
    context.user_data["upload_category"] = text
    await update.message.reply_text(
        f"📂 دسته: {text}\n\nفایل PDF یا عکس را بفرستید:",
        reply_markup=ReplyKeyboardMarkup([["❌ انصراف"]], resize_keyboard=True),
    )
    return UPLOAD_FILE


async def upload_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.text == "❌ انصراف":
        await msg.reply_text("لغو شد.", reply_markup=ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True))
        return ADMIN_MENU

    if msg.document:
        context.user_data["file_id"] = msg.document.file_id
        context.user_data["file_type"] = "document"
        context.user_data["original_filename"] = msg.document.file_name
        context.user_data["caption"] = msg.caption or ""
    elif msg.photo:
        context.user_data["file_id"] = msg.photo[-1].file_id
        context.user_data["file_type"] = "photo"
        context.user_data["original_filename"] = None
        context.user_data["caption"] = msg.caption or ""
    else:
        await msg.reply_text("لطفاً PDF یا عکس بفرستید.")
        return UPLOAD_FILE

    await msg.reply_text("یادداشت قیمت را بنویسید یا /skip")
    return UPLOAD_NOTE


async def upload_note_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    note = None if text.strip() == "/skip" else text
    catalog_id = db.add_catalog(
        category=context.user_data["upload_category"],
        file_id=context.user_data["file_id"],
        file_type=context.user_data["file_type"],
        caption=context.user_data.get("caption"),
        custom_note=note,
        uploaded_by=update.effective_user.id,
        original_filename=context.user_data.get("original_filename"),
    )
    await update.message.reply_text(
        f"✅ فایل #{catalog_id} ذخیره شد.",
        reply_markup=ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True),
    )
    context.user_data.clear()
    return ADMIN_MENU


async def delete_cat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    if text == "❌ انصراف":
        await update.message.reply_text("لغو شد.", reply_markup=ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True))
        return ADMIN_MENU

    catalogs = db.get_catalogs(text)
    if not catalogs:
        await update.message.reply_text("فایلی یافت نشد.")
        return ADMIN_MENU

    lines = [f"📂 {text}:", ""]
    for c in catalogs:
        fname = c["original_filename"] or c["file_type"]
        extra = f" — ({c['custom_note']})" if c["custom_note"] else ""
        lines.append(f"🔹 #{c['id']} — {fname}{extra}")
    lines.append("")
    lines.append("ID فایل برای حذف را بفرستید یا /cancel")
    await update.message.reply_text("\n".join(lines))
    return DELETE_SELECT_ITEM


async def delete_item_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text == "/cancel":
        await update.message.reply_text("لغو شد.", reply_markup=ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True))
        return ADMIN_MENU
    try:
        catalog_id = int(text)
    except ValueError:
        await update.message.reply_text("یک عدد وارد کنید.")
        return DELETE_SELECT_ITEM

    cat = db.get_catalog_by_id(catalog_id)
    if not cat:
        await update.message.reply_text("فایل یافت نشد.")
    else:
        db.delete_catalog(catalog_id)
        await update.message.reply_text(f"✅ فایل #{catalog_id} حذف شد.")

    await update.message.reply_text("پنل مدیریت:", reply_markup=ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True))
    return ADMIN_MENU


async def edit_contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    if text.strip() == "/cancel":
        await update.message.reply_text("لغو شد.", reply_markup=ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True))
        return ADMIN_MENU
    db.set_setting("contact_text", text)
    await update.message.reply_text("✅ اطلاعات تماس ذخیره شد.", reply_markup=ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True))
    return ADMIN_MENU


async def broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    if text.strip() == "/cancel":
        await update.message.reply_text("لغو شد.", reply_markup=ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True))
        return ADMIN_MENU

    user_ids = db.get_active_user_ids()
    sent = failed = 0
    status = await update.message.reply_text(f"📢 ارسال به {len(user_ids)} کاربر...")

    for uid in user_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=text)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    db.log_broadcast(text, sent, failed, update.effective_user.id)
    try:
        await status.edit_text(f"✅ تمام شد\n✅ {sent}\n❌ {failed}")
    except Exception:
        pass
    await update.message.reply_text("پنل مدیریت:", reply_markup=ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True))
    return ADMIN_MENU


async def restore_db_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.text and msg.text.strip() == "/cancel":
        await msg.reply_text("لغو شد.", reply_markup=ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True))
        return ADMIN_MENU
    if not msg.document:
        await msg.reply_text("فایل .db بفرستید.")
        return RESTORE_DB
    try:
        tg_file = await context.bot.get_file(msg.document.file_id)
        path = f"/tmp/restore_{int(__import__('time').time())}.db"
        await tg_file.download_to_drive(path)
        db.restore_from_file(path)
        if os.path.exists(path):
            os.remove(path)
        await msg.reply_text("✅ بازگردانی انجام شد.", reply_markup=ReplyKeyboardMarkup(ADMIN_KEYBOARD, resize_keyboard=True))
    except Exception as e:
        await msg.reply_text(f"⚠️ خطا: {e}")
    return ADMIN_MENU


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لغو شد.", reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True))
    return ConversationHandler.END


def create_bot_app():
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("BOT_TOKEN is empty")

    app = (
        Application.builder()
        .token(token)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .build()
    )

    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ADMIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler)],
            UPLOAD_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_category_handler)],
            UPLOAD_FILE: [
                MessageHandler(filters.Document.ALL | filters.PHOTO, upload_file_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, upload_file_handler),
            ],
            UPLOAD_NOTE: [MessageHandler(filters.TEXT, upload_note_handler)],
            DELETE_SELECT_CAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_cat_handler)],
            DELETE_SELECT_ITEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_item_handler)],
            EDIT_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_contact_handler)],
            BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_handler)],
            RESTORE_DB: [
                MessageHandler(filters.Document.ALL, restore_db_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, restore_db_handler),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(admin_conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex(BUTTON_REGEX), handle_menu))

    # unknown text fallback so users get a reply
    async def fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "لطفاً از منوی زیر یک گزینه را انتخاب کنید:",
            reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True),
        )

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))
    return app
