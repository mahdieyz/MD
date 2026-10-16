import os
import logging
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)
from database import Database

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
db = Database()

TOKEN = os.getenv("BOT_TOKEN", "")


def parse_admin_ids():
    raw = os.getenv("ADMIN_IDS", "")
    clean = raw.replace('"', '').replace("'", "").replace("[", "").replace("]", "")
    ids = []
    for part in clean.split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids


ADMIN_IDS = parse_admin_ids()

# Admin Conversation States
ADD_BTN, RENAME_BTN, UPLOAD_FILE, UPLOAD_NOTE, SET_CONTACT, BROADCAST = range(6)

DEFAULT_WELCOME = "سلام {name} عزیز! 👋\nبه ربات توان سازه خوش آمدید.\nجهت دریافت لیست قیمت و کاتالوگ، از منوی زیر استفاده کنید:"
DEFAULT_CONTACT = "📞 *ارتباط با واحد فروش توان سازه*\n\n📲 تلفن: 021-12345678\n👤 پشتیبانی تلگرام: @Tavansazeh_Admin"


def is_admin(uid):
    return int(uid) in ADMIN_IDS


# ── DYNAMIC KEYBOARDS ──

def build_menu_kb(path, user_id):
    parent_id = path[-1] if path else 0
    buttons = db.get_buttons(parent_id)

    rows, row = [], []
    for b in buttons:
        row.append(KeyboardButton(b["title"]))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    if path:
        rows.append([KeyboardButton("🔙 بازگشت"), KeyboardButton("🏠 منوی اصلی")])
    else:
        rows.append([KeyboardButton("🛒 ثبت سفارش / تماس با ما")])
        if is_admin(user_id):
            rows.append([KeyboardButton("🔧 پنل مدیریت")])

    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def main_menu_kb(user_id):
    return build_menu_kb([], user_id)


def admin_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗂️ مدیریت منو، گروه‌ها و فایل‌ها", callback_data="adm_tree_0")],
        [InlineKeyboardButton("📞 تنظیم اطلاعات تماس", callback_data="adm_contact")],
        [InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="adm_broadcast")],
        [InlineKeyboardButton("📊 آمار ربات", callback_data="adm_stats")],
    ])


def build_tree_kb(parent_id):
    buttons = db.get_buttons(parent_id)
    kb = []
    for b in buttons:
        kb.append([
            InlineKeyboardButton(f"📁 {b['title']}", callback_data=f"adm_tree_{b['id']}"),
            InlineKeyboardButton("✏️", callback_data=f"adm_renamebtn_{b['id']}"),
            InlineKeyboardButton("🗑️", callback_data=f"adm_delbtn_{b['id']}_{parent_id}"),
        ])
    kb.append([InlineKeyboardButton("➕ افزودن دکمه/گروه جدید", callback_data=f"adm_addbtn_{parent_id}")])
    kb.append([InlineKeyboardButton("📤 آپلود فایل در این بخش", callback_data=f"adm_addcat_{parent_id}")])

    files = db.get_catalogs(parent_id)
    if files:
        kb.append([InlineKeyboardButton(f"📄 مدیریت فایل‌های این بخش ({len(files)})", callback_data=f"adm_catlist_{parent_id}")])

    if parent_id != 0:
        parent = db.get_button(parent_id)
        back_to = parent["parent_id"] if parent else 0
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"adm_tree_{back_to}")])

    kb.append([InlineKeyboardButton("🏠 منوی مدیریت", callback_data="admmenu")])
    return InlineKeyboardMarkup(kb)


# ── USER-SIDE HANDLERS ──

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["menu_path"] = []
    u = update.effective_user
    db.add_user(u.id, u.username, u.first_name, u.last_name)
    welcome = db.get_setting("welcome_text", "") or DEFAULT_WELCOME.format(name=u.first_name or "")
    await update.effective_message.reply_text(welcome, reply_markup=main_menu_kb(u.id))
    return ConversationHandler.END


async def show_menu_keyboard(update: Update, ctx, path, text):
    user_id = update.effective_user.id
    await update.message.reply_text(text, reply_markup=build_menu_kb(path, user_id))


async def enter_button(update: Update, ctx, btn, path):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    files = db.get_catalogs(btn["id"])
    children = db.get_buttons(btn["id"])

    if files:
        await update.message.reply_text(f"⏳ در حال ارسال فایل‌های «{btn['title']}»...")
        for item in files:
            try:
                if item.get("file_type") == "photo":
                    await ctx.bot.send_photo(chat_id=chat_id, photo=item["file_id"], caption=item["note"] or None)
                else:
                    await ctx.bot.send_document(chat_id=chat_id, document=item["file_id"], caption=item["note"] or None)
            except Exception as e:
                logger.error(f"Error sending file: {e}")

    if children:
        await update.message.reply_text(
            f"لطفاً گزینه مورد نظر را از «{btn['title']}» انتخاب کنید:",
            reply_markup=build_menu_kb(path, user_id)
        )
    elif files:
        await update.message.reply_text("✅ تمام فایل‌ها ارسال شدند.", reply_markup=build_menu_kb(path, user_id))
    else:
        await update.message.reply_text(
            f"📂 هنوز محتوایی برای «{btn['title']}» ثبت نشده است.\nبه زودی اضافه خواهد شد.",
            reply_markup=build_menu_kb(path, user_id)
        )


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return

    text = msg.text
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name, user.last_name)

    path = ctx.user_data.get("menu_path", [])

    if text == "🏠 منوی اصلی":
        ctx.user_data["menu_path"] = []
        await show_menu_keyboard(update, ctx, [], "به منوی اصلی بازگشتید 👇")
        return

    if text == "🔙 بازگشت":
        new_path = path[:-1]
        ctx.user_data["menu_path"] = new_path
        label = "منوی اصلی" if not new_path else db.get_button(new_path[-1])["title"]
        await show_menu_keyboard(update, ctx, new_path, f"بازگشت به «{label}» 👇")
        return

    if text == "🛒 ثبت سفارش / تماس با ما":
        contact = db.get_setting("contact_text", "") or DEFAULT_CONTACT
        await msg.reply_text(contact, parse_mode="Markdown", reply_markup=build_menu_kb(path, user.id))
        return

    if text == "🔧 پنل مدیریت" and is_admin(user.id):
        await admin_cmd(update, ctx)
        return

    parent_id = path[-1] if path else 0
    btn = db.get_button_by_title_parent(text, parent_id)
    if not btn:
        await msg.reply_text("لطفاً از دکمه‌های موجود در کیبورد استفاده کنید 👇", reply_markup=build_menu_kb(path, user.id))
        return

    new_path = path + [btn["id"]]
    ctx.user_data["menu_path"] = new_path
    await enter_button(update, ctx, btn, new_path)


# ── ADMIN PANEL ──

async def admin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return ConversationHandler.END
    await update.effective_message.reply_text(
        "🔧 *پنل مدیریت ربات*\nگزینه مورد نظر را انتخاب کنید:",
        parse_mode="Markdown", reply_markup=admin_menu_kb()
    )
    return ConversationHandler.END


async def admin_cb_dispatch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """پیمایش منو/آمار/حذف فایل/حذف دکمه - بدون نیاز به گفتگوی چندمرحله‌ای"""
    q = update.callback_query
    if not is_admin(update.effective_user.id):
        await q.answer("دسترسی غیرمجاز!", show_alert=True)
        return
    data = q.data
    await q.answer()

    if data == "admmenu":
        await q.edit_message_text(
            "🔧 *پنل مدیریت ربات*\nگزینه مورد نظر را انتخاب کنید:",
            parse_mode="Markdown", reply_markup=admin_menu_kb()
        )

    elif data == "adm_stats":
        s = db.get_stats()
        await q.edit_message_text(
            f"📊 *آمار ربات*\n\n👥 کاربران: {s['total_users']}\n"
            f"📁 کل فایل‌های آپلود شده: {s['total_files']}\n"
            f"🗂️ تعداد دکمه‌ها/گروه‌ها: {s['total_buttons']}",
            parse_mode="Markdown", reply_markup=admin_menu_kb()
        )

    elif data.startswith("adm_tree_"):
        parent_id = int(data.split("_")[-1])
        btn = db.get_button(parent_id) if parent_id != 0 else None
        title = btn["title"] if btn else "منوی اصلی (ریشه)"
        await q.edit_message_text(f"📂 *مدیریت بخش:* {title}", parse_mode="Markdown", reply_markup=build_tree_kb(parent_id))

    elif data.startswith("adm_catlist_"):
        button_id = int(data.split("_")[-1])
        await _show_catlist(q, button_id)

    elif data.startswith("adm_delfile_"):
        parts = data.split("_")
        catalog_id, button_id = int(parts[-2]), int(parts[-1])
        db.delete_catalog(catalog_id)
        await _show_catlist(q, button_id, prefix="✅ فایل حذف شد.\n\n")

    elif data.startswith("adm_delbtn_yes_"):
        parts = data.split("_")
        button_id, parent_id = int(parts[-2]), int(parts[-1])
        db.delete_button(button_id)
        await q.edit_message_text(
            "✅ دکمه/گروه و تمامی زیرمجموعه‌ها و فایل‌های آن حذف شدند.",
            reply_markup=build_tree_kb(parent_id)
        )

    elif data.startswith("adm_delbtn_"):
        parts = data.split("_")
        button_id, parent_id = int(parts[-2]), int(parts[-1])
        btn = db.get_button(button_id)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ بله، حذف شود", callback_data=f"adm_delbtn_yes_{button_id}_{parent_id}")],
            [InlineKeyboardButton("❌ انصراف", callback_data=f"adm_tree_{parent_id}")]
        ])
        await q.edit_message_text(
            f"⚠️ آیا از حذف «{btn['title']}» و تمام زیرمجموعه‌ها/فایل‌های آن مطمئن هستید؟",
            reply_markup=kb
        )


async def _show_catlist(q, button_id, prefix=""):
    files = db.get_catalogs(button_id)
    kb = []
    for f in files:
        label = f["file_name"] or f"فایل #{f['id']}"
        kb.append([InlineKeyboardButton(f"🗑️ {label}", callback_data=f"adm_delfile_{f['id']}_{button_id}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"adm_tree_{button_id}")])
    text = prefix + ("📄 فایل‌های این بخش (برای حذف لمس کنید):" if files else "فایلی ثبت نشده است.")
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))


# ── CONVERSATIONS: add / rename button, upload file, contact, broadcast ──

async def prompt_add_btn(update, ctx):
    q = update.callback_query
    await q.answer()
    parent_id = int(q.data.split("_")[-1])
    ctx.user_data["target_parent_id"] = parent_id
    await q.message.reply_text("✏️ عنوان دکمه/گروه جدید را ارسال کنید:\n(برای انصراف: /cancel)")
    return ADD_BTN


async def save_new_btn(update, ctx):
    title = (update.message.text or "").strip()
    parent_id = ctx.user_data.get("target_parent_id", 0)
    if not title:
        await update.message.reply_text("⚠️ عنوان نامعتبر است. دوباره ارسال کنید:")
        return ADD_BTN
    db.add_button(title, parent_id)
    await update.message.reply_text(f"✅ دکمه «{title}» اضافه شد.")
    await update.message.reply_text("📂 مدیریت این بخش:", reply_markup=build_tree_kb(parent_id))
    return ConversationHandler.END


async def prompt_rename_btn(update, ctx):
    q = update.callback_query
    await q.answer()
    button_id = int(q.data.split("_")[-1])
    ctx.user_data["target_rename_id"] = button_id
    btn = db.get_button(button_id)
    await q.message.reply_text(f"✏️ عنوان جدید برای «{btn['title']}» را ارسال کنید:\n(برای انصراف: /cancel)")
    return RENAME_BTN


async def save_rename_btn(update, ctx):
    title = (update.message.text or "").strip()
    button_id = ctx.user_data.get("target_rename_id")
    if not title or not button_id:
        await update.message.reply_text("⚠️ خطا رخ داد. دوباره تلاش کنید.")
        return ConversationHandler.END
    db.rename_button(button_id, title)
    btn = db.get_button(button_id)
    await update.message.reply_text(f"✅ عنوان به «{title}» تغییر یافت.")
    await update.message.reply_text("📂 مدیریت این بخش:", reply_markup=build_tree_kb(btn["parent_id"]))
    return ConversationHandler.END


async def prompt_add_cat(update, ctx):
    q = update.callback_query
    await q.answer()
    button_id = int(q.data.split("_")[-1])
    ctx.user_data["target_cat_button_id"] = button_id
    btn = db.get_button(button_id) if button_id != 0 else {"title": "منوی اصلی"}
    await q.message.reply_text(f"📄 فایل PDF یا تصویر مربوط به «{btn['title']}» را ارسال کنید:\n(برای انصراف: /cancel)")
    return UPLOAD_FILE


async def upload_file_receive(update, ctx):
    msg = update.message
    if msg.document:
        ctx.user_data["upload_file_id"] = msg.document.file_id
        ctx.user_data["upload_file_name"] = msg.document.file_name or ""
        ctx.user_data["upload_file_type"] = "document"
    elif msg.photo:
        ctx.user_data["upload_file_id"] = msg.photo[-1].file_id
        ctx.user_data["upload_file_name"] = ""
        ctx.user_data["upload_file_type"] = "photo"
    else:
        await msg.reply_text("⚠️ لطفاً فایل را به صورت تصویر یا داکیومنت (PDF) ارسال کنید:")
        return UPLOAD_FILE

    await msg.reply_text("📝 اگر توضیحی دارید وارد کنید (مثلاً «لیست بعلاوه ۲۰ درصد»)، یا عدد 0 را بفرستید:")
    return UPLOAD_NOTE


async def upload_note_receive(update, ctx):
    note = (update.message.text or "").strip()
    if note in ("0", "-"):
        note = ""

    button_id = ctx.user_data.get("target_cat_button_id", 0)
    file_id = ctx.user_data.get("upload_file_id")
    file_name = ctx.user_data.get("upload_file_name", "")
    file_type = ctx.user_data.get("upload_file_type", "document")

    db.add_catalog(button_id, file_id, file_name, note, file_type)

    await update.message.reply_text(
        "✅ فایل با موفقیت ذخیره و به بخش مربوطه متصل شد.",
        reply_markup=main_menu_kb(update.effective_user.id)
    )
    return ConversationHandler.END


async def prompt_contact(update, ctx):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("📝 متن جدید بخش «تماس با ما / ثبت سفارش» را ارسال کنید:\n(برای انصراف: /cancel)")
    return SET_CONTACT


async def set_contact_receive(update, ctx):
    db.set_setting("contact_text", update.message.text)
    await update.message.reply_text("✅ اطلاعات تماس بروزرسانی شد.", reply_markup=main_menu_kb(update.effective_user.id))
    return ConversationHandler.END


async def prompt_broadcast(update, ctx):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("📢 متن پیام همگانی را ارسال کنید:\n(برای انصراف: /cancel)")
    return BROADCAST


async def broadcast_receive(update, ctx):
    text = update.message.text
    users = db.get_all_users()
    ok, failed = 0, 0
    for u in users:
        try:
            await ctx.bot.send_message(u["user_id"], text)
            ok += 1
        except Exception:
            failed += 1
    await update.message.reply_text(
        f"✅ پیام همگانی ارسال شد.\nموفق: {ok}\nناموفق: {failed}",
        reply_markup=main_menu_kb(update.effective_user.id)
    )
    return ConversationHandler.END


def _clear_conv_keys(ctx):
    for k in ("target_parent_id", "target_rename_id", "target_cat_button_id",
              "upload_file_id", "upload_file_name", "upload_file_type"):
        ctx.user_data.pop(k, None)


async def cancel(update, ctx):
    _clear_conv_keys(ctx)
    await update.effective_message.reply_text(
        "❌ عملیات لغو شد.", reply_markup=main_menu_kb(update.effective_user.id)
    )
    return ConversationHandler.END


# ── Safety-net fallbacks (prevent stuck conversations) ──

async def conv_fallback_text(update, ctx):
    _clear_conv_keys(ctx)
    await handle_message(update, ctx)
    return ConversationHandler.END


async def conv_fallback_callback(update, ctx):
    _clear_conv_keys(ctx)
    await admin_cb_dispatch(update, ctx)
    return ConversationHandler.END


async def error_handler(update, ctx):
    logger.error("Exception while handling an update:", exc_info=ctx.error)


# ── MAIN ENGINE ──

def main():
    if not TOKEN:
        logging.error("BOT_TOKEN is missing!")
        return

    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(prompt_add_btn, pattern="^adm_addbtn_"),
            CallbackQueryHandler(prompt_rename_btn, pattern="^adm_renamebtn_"),
            CallbackQueryHandler(prompt_add_cat, pattern="^adm_addcat_"),
            CallbackQueryHandler(prompt_contact, pattern="^adm_contact$"),
            CallbackQueryHandler(prompt_broadcast, pattern="^adm_broadcast$"),
        ],
        states={
            ADD_BTN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_btn)],
            RENAME_BTN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_rename_btn)],
            UPLOAD_FILE: [MessageHandler(filters.Document.ALL | filters.PHOTO, upload_file_receive)],
            UPLOAD_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_note_receive)],
            SET_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_contact_receive)],
            BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_receive)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            CommandHandler("admin", admin_cmd),
            CallbackQueryHandler(conv_fallback_callback),
            MessageHandler(filters.TEXT & ~filters.COMMAND, conv_fallback_text),
        ],
        allow_reentry=True,
    )

    # مهم: conv_handler باید قبل از دستورات ساده ثبت شود، در غیر این صورت
    # هنگام فعال بودن یک گفتگو، fallback های آن هرگز اجرا نمی‌شوند و
    # گفتگو برای همیشه "گیر" می‌کند (باگ بحرانی نسخه‌ی قبلی که می‌توانست
    # باعث ارسال پیام همگانی ناخواسته شود).
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(
        admin_cb_dispatch,
        pattern="^(admmenu|adm_stats|adm_tree_|adm_catlist_|adm_delfile_|adm_delbtn_)"
    ))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logging.info("🤖 Bot is active...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
