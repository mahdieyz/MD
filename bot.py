import os
import logging
from datetime import datetime
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

(ADD_BTN, RENAME_BTN, UPLOAD_FILE, UPLOAD_NOTE,
 SET_CONTACT, BROADCAST, RESTORE_DB) = range(7)

CONTACT_BTN = "🛒 ثبت سفارش / تماس با ما"
ADMIN_BTN = "🔧 پنل مدیریت"
BACK_BTN = "🔙 بازگشت"
HOME_BTN = "🏠 منوی اصلی"


def is_admin(uid):
    return int(uid) in ADMIN_IDS


# ── DYNAMIC REPLY KEYBOARDS ──

def build_menu_kb(path, user_id):
    parent_id = path[-1] if path else 0
    buttons = db.get_buttons(parent_id)

    rows, row = [], []
    for b in buttons:
        row.append(KeyboardButton(b["title"]))
        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)

    if path:
        rows.append([KeyboardButton(BACK_BTN), KeyboardButton(HOME_BTN)])
    else:
        rows.append([KeyboardButton(CONTACT_BTN)])
        if is_admin(user_id):
            rows.append([KeyboardButton(ADMIN_BTN)])

    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def main_menu_kb(user_id):
    return build_menu_kb([], user_id)


# ── ADMIN INLINE KEYBOARDS ──

def admin_home_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗂️ مدیریت منو، گروه‌ها و فایل‌ها", callback_data="admtree_0")],
        [InlineKeyboardButton("📞 اطلاعات تماس", callback_data="admcontact"),
         InlineKeyboardButton("📢 پیام همگانی", callback_data="admbroadcast")],
        [InlineKeyboardButton("💾 دانلود بکاپ", callback_data="admbackup"),
         InlineKeyboardButton("📥 بازگردانی بکاپ", callback_data="admrestore")],
        [InlineKeyboardButton("📊 آمار", callback_data="admstats")],
        [InlineKeyboardButton("⚠️ ریست منو و فایل‌ها", callback_data="admresetmenu")],
    ])


def build_tree_kb(parent_id):
    buttons = db.get_buttons(parent_id)
    kb = []
    for i, b in enumerate(buttons):
        kb.append([
            InlineKeyboardButton(f"📁 {b['title']}", callback_data=f"admtree_{b['id']}"),
            InlineKeyboardButton("✏️", callback_data=f"admrenamebtn_{b['id']}"),
            InlineKeyboardButton("🗑️", callback_data=f"admdelbtn_{b['id']}_{parent_id}"),
        ])
        nav = []
        if i > 0:
            nav.append(InlineKeyboardButton("⬆️", callback_data=f"admmoveup_{b['id']}_{parent_id}"))
        if i < len(buttons) - 1:
            nav.append(InlineKeyboardButton("⬇️", callback_data=f"admmovedown_{b['id']}_{parent_id}"))
        if nav:
            kb.append(nav)

    kb.append([InlineKeyboardButton("➕ افزودن دکمه/گروه جدید", callback_data=f"admaddbtn_{parent_id}")])
    kb.append([InlineKeyboardButton("📤 آپلود فایل در این بخش", callback_data=f"admaddfile_{parent_id}")])

    files = db.get_catalogs(parent_id)
    if files:
        kb.append([InlineKeyboardButton(f"📄 مدیریت فایل‌های این بخش ({len(files)})", callback_data=f"admfiles_{parent_id}")])

    if parent_id != 0:
        parent = db.get_button(parent_id)
        back_to = parent["parent_id"] if parent else 0
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"admtree_{back_to}")])

    kb.append([InlineKeyboardButton("🏠 منوی مدیریت", callback_data="admhome")])
    return InlineKeyboardMarkup(kb)


# ── USER-SIDE ──

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    ctx.user_data["menu_path"] = []
    u = update.effective_user
    db.add_user(u.id, u.username, u.first_name, u.last_name)

    template = db.get_setting("welcome_text")
    if template:
        welcome = template.replace("{name}", u.first_name or "کاربر")
    else:
        welcome = (f"سلام {u.first_name or 'کاربر'} عزیز! 👋\n"
                   "به ربات توان سازه خوش آمدید.\n"
                   "جهت دریافت لیست قیمت و کاتالوگ، از منوی زیر استفاده کنید:")
    await update.effective_message.reply_text(welcome, reply_markup=main_menu_kb(u.id))
    return ConversationHandler.END


async def enter_button(update: Update, ctx, btn, path):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    files = db.get_catalogs(btn["id"])
    children = db.get_buttons(btn["id"])

    if files:
        await update.message.reply_text(f"⏳ در حال ارسال فایل‌های «{btn['title']}»...")
        sent = 0
        for item in files:
            try:
                if item.get("file_type") == "photo":
                    await ctx.bot.send_photo(chat_id=chat_id, photo=item["file_id"], caption=item["note"] or None)
                else:
                    await ctx.bot.send_document(chat_id=chat_id, document=item["file_id"], caption=item["note"] or None)
                sent += 1
            except Exception as e:
                logger.error(f"Send file fail: {e}")

    if children:
        await update.message.reply_text(
            f"لطفاً گزینه مورد نظر را از «{btn['title']}» انتخاب کنید:",
            reply_markup=build_menu_kb(path, user_id))
    elif files:
        await update.message.reply_text(f"✅ {sent} فایل ارسال شد.", reply_markup=build_menu_kb(path, user_id))
    else:
        await update.message.reply_text(
            f"📂 هنوز کاتالوگی برای «{btn['title']}» ثبت نشده است.\nبه زودی لیست قیمت جدید قرار می‌گیرد.",
            reply_markup=build_menu_kb(path, user_id))


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return

    text = msg.text
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name, user.last_name)

    path = ctx.user_data.get("menu_path", [])

    if text == HOME_BTN:
        ctx.user_data["menu_path"] = []
        await msg.reply_text("منوی اصلی 👇", reply_markup=main_menu_kb(user.id))
        return

    if text == BACK_BTN:
        new_path = path[:-1]
        ctx.user_data["menu_path"] = new_path
        label = "منوی اصلی" if not new_path else db.get_button(new_path[-1])["title"]
        await msg.reply_text(f"بازگشت به «{label}» 👇", reply_markup=build_menu_kb(new_path, user.id))
        return

    if text == CONTACT_BTN:
        contact = db.get_setting("contact_text",
            "📞 *ارتباط با واحد فروش توان سازه*\n\n📲 تلفن: 021-12345678\n👤 پشتیبانی: @Tavansazeh_Admin")
        await msg.reply_text(contact, parse_mode="Markdown", reply_markup=build_menu_kb(path, user.id))
        return

    if text == ADMIN_BTN and is_admin(user.id):
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
        await update.effective_message.reply_text("⛔ دسترسی ندارید.")
        return ConversationHandler.END
    await update.effective_message.reply_text(
        "🔧 *پنل مدیریت ربات*", parse_mode="Markdown", reply_markup=admin_home_kb())
    return ConversationHandler.END


async def admin_cb_dispatch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("⛔ دسترسی ندارید.", show_alert=True)
        return
    data = q.data
    await q.answer()

    if data == "admhome":
        await q.edit_message_text("🔧 *پنل مدیریت ربات*", parse_mode="Markdown", reply_markup=admin_home_kb())
        return

    if data == "admstats":
        s = db.get_stats()
        breakdown = db.get_section_breakdown()
        details = "\n".join(f"  • {t}: {c}" for t, c in breakdown) or "  (هنوز فایلی ثبت نشده)"
        await q.edit_message_text(
            f"📊 *آمار ربات*\n\n👥 کاربران: {s['total_users']}\n"
            f"📁 کل فایل‌ها: {s['total_files']}\n🗂️ تعداد دکمه‌ها/گروه‌ها: {s['total_buttons']}\n\n"
            f"📦 *توزیع فایل‌ها بر اساس بخش:*\n{details}",
            parse_mode="Markdown", reply_markup=admin_home_kb())
        return

    if data == "admbackup":
        if not os.path.exists(db.db_name):
            await q.edit_message_text("⚠️ فایل دیتابیس یافت نشد.", reply_markup=admin_home_kb())
            return
        await q.edit_message_text("⏳ در حال ساخت بکاپ امن...")
        try:
            backup_path = db.db_name + ".backup"
            db.backup_to_file(backup_path)
            with open(backup_path, "rb") as f:
                await ctx.bot.send_document(
                    chat_id=q.message.chat_id, document=f,
                    filename=f"backup_{datetime.now():%Y%m%d_%H%M}.db",
                    caption="💾 بکاپ دیتابیس ربات (شامل منو، کاتالوگ، کاربران و تنظیمات)")
            os.remove(backup_path)
            await q.message.reply_text("✅ بکاپ ارسال شد.", reply_markup=admin_home_kb())
        except Exception as e:
            logger.error(f"Backup error: {e}")
            await q.message.reply_text(f"❌ خطا در بکاپ: {e}", reply_markup=admin_home_kb())
        return

    if data == "admresetmenu":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ بله، منو ریست شود", callback_data="admresetmenuyes")],
            [InlineKeyboardButton("❌ انصراف", callback_data="admhome")]
        ])
        await q.edit_message_text(
            "⚠️ آیا مطمئن هستید؟ تمام دکمه‌ها، گروه‌ها و فایل‌های آپلودی پاک شده و به حالت اولیه بازمی‌گردند.\n"
            "(کاربران و تنظیمات متنی پاک نخواهند شد)", reply_markup=kb)
        return

    if data == "admresetmenuyes":
        ok = db.reset_menu()
        msg = "✅ منو با موفقیت ریست شد." if ok else "❌ خطا در ریست منو."
        await q.edit_message_text(msg, reply_markup=admin_home_kb())
        return

    if data.startswith("admtree_"):
        parent_id = int(data.split("_")[1])
        btn = db.get_button(parent_id) if parent_id != 0 else None
        title = btn["title"] if btn else "منوی اصلی (ریشه)"
        await q.edit_message_text(f"📂 *مدیریت بخش:* {title}", parse_mode="Markdown", reply_markup=build_tree_kb(parent_id))
        return

    if data.startswith("admmoveup_") or data.startswith("admmovedown_"):
        parts = data.split("_")
        direction = "up" if data.startswith("admmoveup_") else "down"
        button_id, parent_id = int(parts[1]), int(parts[2])
        db.move_button(button_id, direction)
        await q.edit_message_text("📂 *مدیریت بخش*", parse_mode="Markdown", reply_markup=build_tree_kb(parent_id))
        return

    if data.startswith("admfiles_"):
        button_id = int(data.split("_")[1])
        await _show_file_list(q, button_id)
        return

    if data.startswith("admdelfile_"):
        parts = data.split("_")
        file_id, button_id = int(parts[1]), int(parts[2])
        db.delete_catalog(file_id)
        await _show_file_list(q, button_id, prefix="✅ فایل حذف شد.\n\n")
        return

    if data.startswith("admdelbtnyes_"):
        parts = data.split("_")
        button_id, parent_id = int(parts[1]), int(parts[2])
        db.delete_button(button_id)
        await q.edit_message_text(
            "✅ دکمه/گروه و تمام زیرمجموعه‌ها و فایل‌های آن حذف شدند.",
            reply_markup=build_tree_kb(parent_id))
        return

    if data.startswith("admdelbtn_"):
        parts = data.split("_")
        button_id, parent_id = int(parts[1]), int(parts[2])
        btn = db.get_button(button_id)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ بله، حذف شود", callback_data=f"admdelbtnyes_{button_id}_{parent_id}")],
            [InlineKeyboardButton("❌ انصراف", callback_data=f"admtree_{parent_id}")]
        ])
        await q.edit_message_text(
            f"⚠️ آیا از حذف «{btn['title']}» و تمام زیرمجموعه‌ها/فایل‌های آن مطمئن هستید؟",
            reply_markup=kb)
        return


async def _show_file_list(q, button_id, prefix=""):
    files = db.get_catalogs(button_id)
    kb = []
    for f in files:
        label = f["file_name"] or f"فایل #{f['id']}"
        kb.append([InlineKeyboardButton(f"🗑️ {label}", callback_data=f"admdelfile_{f['id']}_{button_id}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"admtree_{button_id}")])
    text = prefix + ("📄 فایل‌های این بخش (برای حذف لمس کنید):" if files else "فایلی ثبت نشده است.")
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))


# ── CONVERSATIONS: add/rename button, upload file, contact, broadcast, restore ──

async def prompt_add_btn(update, ctx):
    q = update.callback_query; await q.answer()
    parent_id = int(q.data.split("_")[1])
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
    q = update.callback_query; await q.answer()
    button_id = int(q.data.split("_")[1])
    ctx.user_data["target_rename_id"] = button_id
    btn = db.get_button(button_id)
    await q.message.reply_text(f"✏️ عنوان جدید برای «{btn['title']}» را ارسال کنید:\n(برای انصراف: /cancel)")
    return RENAME_BTN


async def save_rename_btn(update, ctx):
    title = (update.message.text or "").strip()
    button_id = ctx.user_data.get("target_rename_id")
    if not title or not button_id:
        await update.message.reply_text("⚠️ خطا رخ داد.")
        return ConversationHandler.END
    db.rename_button(button_id, title)
    btn = db.get_button(button_id)
    await update.message.reply_text(f"✅ عنوان به «{title}» تغییر یافت.")
    await update.message.reply_text("📂 مدیریت این بخش:", reply_markup=build_tree_kb(btn["parent_id"]))
    return ConversationHandler.END


async def prompt_add_file(update, ctx):
    q = update.callback_query; await q.answer()
    button_id = int(q.data.split("_")[1])
    ctx.user_data["target_cat_button_id"] = button_id
    btn = db.get_button(button_id) if button_id != 0 else {"title": "منوی اصلی"}
    await q.message.reply_text(f"📄 فایل PDF یا تصویر مربوط به «{btn['title']}» را ارسال کنید:\n(برای انصراف: /cancel)")
    return UPLOAD_FILE


async def upload_file_receive(update, ctx):
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
        "📝 فایل دریافت شد!\n\nاگر توضیحی دارید وارد کنید (مثلاً «لیست بعلاوه ۲۰ درصد»)، یا عدد 0 را بفرستید:")
    return UPLOAD_NOTE


async def upload_note_receive(update, ctx):
    note = (update.message.text or "").strip()
    if note == "0":
        note = ""
    button_id = ctx.user_data.get("target_cat_button_id", 0)
    db.add_catalog_file(
        button_id=button_id,
        file_id=ctx.user_data["upload_file_id"],
        file_name=ctx.user_data["upload_file_name"],
        note=note,
        file_type=ctx.user_data["upload_file_type"])
    await update.message.reply_text("✅ فایل با موفقیت ذخیره و به بخش متصل شد!", reply_markup=main_menu_kb(update.effective_user.id))
    return ConversationHandler.END


async def prompt_contact(update, ctx):
    q = update.callback_query; await q.answer()
    cur = db.get_setting("contact_text", "(خالی)")
    await q.message.reply_text(f"📝 متن فعلی:\n\n{cur}\n\n──────────\nمتن جدید را ارسال کنید:\n(برای انصراف: /cancel)")
    return SET_CONTACT


async def set_contact_receive(update, ctx):
    db.set_setting("contact_text", update.message.text)
    await update.message.reply_text("✅ اطلاعات تماس بروزرسانی شد.", reply_markup=main_menu_kb(update.effective_user.id))
    return ConversationHandler.END


async def prompt_broadcast(update, ctx):
    q = update.callback_query; await q.answer()
    await q.message.reply_text("📢 متن پیام همگانی را ارسال کنید:\n(برای انصراف: /cancel)")
    return BROADCAST


async def broadcast_receive(update, ctx):
    text = update.message.text
    users = db.get_all_users()
    await update.message.reply_text(f"⏳ ارسال به {len(users)} کاربر...")
    ok, fail = 0, 0
    for u in users:
        try:
            await ctx.bot.send_message(u["user_id"], text[:4000])
            ok += 1
        except Exception:
            fail += 1
    await update.message.reply_text(
        f"✅ گزارش ارسال:\n├ موفق: {ok}\n└ ناموفق: {fail}",
        reply_markup=main_menu_kb(update.effective_user.id))
    return ConversationHandler.END


async def prompt_restore(update, ctx):
    q = update.callback_query; await q.answer()
    await q.message.reply_text(
        "📥 فایل بکاپ (`.db`) را ارسال کنید.\n\n⚠️ دیتابیس فعلی به‌طور خودکار پشتیبان‌گیری می‌شود.\n(برای انصراف: /cancel)",
        parse_mode="Markdown")
    return RESTORE_DB


async def restore_db_receive(update, ctx):
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
        await msg.reply_text("✅ دیتابیس با موفقیت بازگردانی شد!", reply_markup=main_menu_kb(update.effective_user.id))
    except Exception as e:
        logger.error(f"Restore fail: {e}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        await msg.reply_text(f"❌ بازگردانی ناموفق: {e}")
    return ConversationHandler.END


def _clear_conv_keys(ctx):
    for k in ("target_parent_id", "target_rename_id", "target_cat_button_id",
              "upload_file_id", "upload_file_name", "upload_file_type"):
        ctx.user_data.pop(k, None)


async def cancel(update, ctx):
    _clear_conv_keys(ctx)
    await update.effective_message.reply_text("❌ عملیات لغو شد.", reply_markup=main_menu_kb(update.effective_user.id))
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


# ── MAIN ──

def main():
    if not TOKEN:
        logger.error("❌ BOT_TOKEN missing!")
        return

    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(prompt_add_btn, pattern="^admaddbtn_"),
            CallbackQueryHandler(prompt_rename_btn, pattern="^admrenamebtn_"),
            CallbackQueryHandler(prompt_add_file, pattern="^admaddfile_"),
            CallbackQueryHandler(prompt_contact, pattern="^admcontact$"),
            CallbackQueryHandler(prompt_broadcast, pattern="^admbroadcast$"),
            CallbackQueryHandler(prompt_restore, pattern="^admrestore$"),
        ],
        states={
            ADD_BTN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_btn)],
            RENAME_BTN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_rename_btn)],
            UPLOAD_FILE: [MessageHandler(filters.Document.ALL | filters.PHOTO, upload_file_receive)],
            UPLOAD_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_note_receive)],
            SET_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_contact_receive)],
            BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_receive)],
            RESTORE_DB: [MessageHandler(filters.Document.ALL, restore_db_receive)],
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
    # هنگام فعال بودن یک گفتگو، fallback های آن هرگز اجرا نمی‌شوند و ممکن
    # است یک پیام همگانی یا بازگردانی دیتابیس به‌اشتباه اجرا شود.
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(
        admin_cb_dispatch,
        pattern="^(admhome|admstats|admbackup|admresetmenu|admresetmenuyes|admtree_|admmoveup_|admmovedown_|admfiles_|admdelfile_|admdelbtn_|admdelbtnyes_)"
    ))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("🤖 Tavansazeh bot is live...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
