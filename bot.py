import os
import logging
from datetime import datetime

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    PicklePersistence,
    filters,
)

from database import Database, DB_PATH

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

db = Database()


def parse_admin_ids():
    raw = os.getenv("ADMIN_IDS", "")
    raw = raw.strip().strip("[]")
    ids = []
    for part in raw.split(","):
        part = part.strip().strip("'").strip('"').strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            logger.warning("Could not parse ADMIN_IDS entry: %r", part)
    return ids


ADMIN_IDS = parse_admin_ids()
TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TOKEN")

if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN (or TOKEN) environment variable is not set. "
        "Set it in Railway's Variables tab."
    )

# ---------- conversation states ----------
(
    ADD_BTN,
    RENAME_BTN,
    UPLOAD_FILE,
    UPLOAD_NOTE,
    ADD_TEXT,
    SET_CONTACT,
    SET_WELCOME,
    BROADCAST,
    RESTORE_DB,
) = range(9)

# ---------- constants ----------
CONTACT_BTN = "🛒 ثبت سفارش / تماس با ما"
ADMIN_BTN = "🔧 پنل مدیریت"
BACK_HOME_BTN = "🔙 بازگشت به منوی اصلی"
DIVIDER = "➖➖➖➖➖➖➖➖➖➖"

GLASS_MODE_KEY = "glass_mode"  # "on" / "off"

WELCOME_TEXT_DEFAULT = (
    "سلام {name} عزیز 👋\n\n"
    "به ربات شرکت توان سازه خوش آمدید.\n"
    "از منوی زیر محصول موردنظر خود را انتخاب کنید."
)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_glass_mode() -> bool:
    return db.get_setting(GLASS_MODE_KEY, "off") == "on"


async def safe_edit(query, text, reply_markup=None):
    """Edit a message, silently ignoring the harmless 'message is not modified' error."""
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


# =========================================================
# USER-FACING MENU — REPLY KEYBOARD MODE (classic)
# =========================================================

def build_menu_kb(parent_id: int, user_id: int = None) -> ReplyKeyboardMarkup:
    buttons = db.get_buttons(parent_id)
    rows, row = [], []
    for b in buttons:
        row.append(b["title"])
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    if parent_id == 0:
        rows.append([CONTACT_BTN])
        if user_id and is_admin(user_id):
            rows.append([ADMIN_BTN])
    else:
        rows.append([BACK_HOME_BTN])

    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, parent_id: int):
    context.user_data["parent_id"] = parent_id
    kb = build_menu_kb(parent_id, update.effective_user.id)
    if parent_id == 0:
        text = "🏠 منوی اصلی"
    else:
        btn = db.get_button(parent_id)
        text = f"📂 {btn['title']}" if btn else "منو"
    await update.message.reply_text(text, reply_markup=kb)


async def _send_section_items(bot, chat_id, items):
    for item in items:
        try:
            ftype = item.get("file_type")
            if ftype == "text":
                content = (item.get("note") or "").strip()
                if content:
                    await bot.send_message(chat_id=chat_id, text=content)
            elif ftype == "photo":
                caption = item.get("note") or item.get("file_name") or ""
                await bot.send_photo(chat_id=chat_id, photo=item["file_id"], caption=caption)
            else:
                caption = item.get("note") or item.get("file_name") or ""
                await bot.send_document(chat_id=chat_id, document=item["file_id"], caption=caption)
        except Exception:
            logger.exception("Failed to send item id=%s", item.get("id"))


async def enter_button(update: Update, context: ContextTypes.DEFAULT_TYPE, btn: dict):
    button_id = btn["id"]
    items = db.get_catalogs(button_id)

    await _send_section_items(context.bot, update.effective_chat.id, items)

    children = db.get_buttons(button_id)
    if children:
        context.user_data["parent_id"] = button_id
        kb = build_menu_kb(button_id, update.effective_user.id)
        await update.message.reply_text(f"📂 {btn['title']}", reply_markup=kb)
    elif not items:
        await update.message.reply_text("ℹ️ محتوایی برای این بخش ثبت نشده است.")


# =========================================================
# USER-FACING MENU — INLINE "GLASS BUTTON" MODE
# =========================================================

def build_menu_inline_kb(parent_id: int, user_id: int = None) -> InlineKeyboardMarkup:
    buttons = db.get_buttons(parent_id)
    rows, row = [], []
    for b in buttons:
        row.append(InlineKeyboardButton(b["title"], callback_data=f"ucat_{b['id']}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    if parent_id == 0:
        rows.append([InlineKeyboardButton(CONTACT_BTN, callback_data="ucontact")])
        if user_id and is_admin(user_id):
            rows.append([InlineKeyboardButton(ADMIN_BTN, callback_data="admhome")])
    else:
        rows.append([InlineKeyboardButton(BACK_HOME_BTN, callback_data="uhome")])

    return InlineKeyboardMarkup(rows)


async def user_cb_dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    await query.answer()

    if data == "uhome":
        await safe_edit(query, "🏠 منوی اصلی", reply_markup=build_menu_inline_kb(0, user_id))
        return

    if data == "ucontact":
        contact_text = db.get_setting(
            "contact_text",
            "برای ثبت سفارش با شماره زیر تماس بگیرید:\n09120000000",
        )
        await context.bot.send_message(chat_id=chat_id, text=contact_text)
        return

    if data.startswith("ucat_"):
        button_id = int(data.split("_")[1])
        btn = db.get_button(button_id)
        if not btn:
            await safe_edit(query, "⚠️ این بخش دیگر موجود نیست.", reply_markup=build_menu_inline_kb(0, user_id))
            return

        items = db.get_catalogs(button_id)
        await _send_section_items(context.bot, chat_id, items)

        children = db.get_buttons(button_id)
        if children:
            await safe_edit(query, f"📂 {btn['title']}", reply_markup=build_menu_inline_kb(button_id, user_id))
        else:
            back_kb = InlineKeyboardMarkup([[InlineKeyboardButton(BACK_HOME_BTN, callback_data="uhome")]])
            if items:
                await safe_edit(query, f"📂 {btn['title']}", reply_markup=back_kb)
            else:
                await safe_edit(query, f"📂 {btn['title']}\n\nℹ️ محتوایی برای این بخش ثبت نشده است.", reply_markup=back_kb)
        return


# =========================================================
# SHARED START / MESSAGE HANDLING
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name)
    context.user_data["parent_id"] = 0

    template = db.get_setting("welcome_text", WELCOME_TEXT_DEFAULT)
    text = template.replace("{name}", user.first_name or "")

    if is_glass_mode():
        await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())
        kb = build_menu_inline_kb(0, user.id)
        await update.message.reply_text("لطفاً یک گزینه را انتخاب کنید 👇", reply_markup=kb)
    else:
        kb = build_menu_kb(0, user.id)
        await update.message.reply_text(text, reply_markup=kb)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == BACK_HOME_BTN:
        await show_menu(update, context, 0)
        return

    if text == CONTACT_BTN:
        contact_text = db.get_setting(
            "contact_text",
            "برای ثبت سفارش با شماره زیر تماس بگیرید:\n09120000000",
        )
        await update.message.reply_text(contact_text)
        return

    if text == ADMIN_BTN:
        await admin_cmd(update, context)
        return

    if is_glass_mode():
        # In glass mode, navigation happens via inline buttons, not typed text.
        kb = build_menu_inline_kb(0, user_id)
        await update.message.reply_text(
            "برای حرکت در منو از دکمه‌های شیشه‌ای زیر پیام استفاده کنید 👇",
            reply_markup=kb,
        )
        return

    current_parent = context.user_data.get("parent_id", 0)
    btn = db.get_button_by_title_parent(text, current_parent)

    # Defensive self-heal: stale keyboard (e.g. after restart) still resolves.
    if not btn and current_parent != 0:
        root_match = db.get_button_by_title_parent(text, 0)
        if root_match:
            btn = root_match
            current_parent = 0

    context.user_data["parent_id"] = current_parent

    if not btn:
        await update.message.reply_text("متوجه نشدم 🤔 منوی اصلی را برایتان باز کردم.")
        await show_menu(update, context, 0)
        return

    await enter_button(update, context, btn)


# =========================================================
# ADMIN PANEL
# =========================================================

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ دسترسی ندارید.")
        return
    await update.message.reply_text(admin_home_text(), reply_markup=admin_home_kb())


def admin_home_text() -> str:
    mode = "🪟 شیشه‌ای (فعال)" if is_glass_mode() else "⌨️ کیبورد معمولی (فعال)"
    return (
        "🔧 <b>پنل مدیریت ربات توان سازه</b>\n"
        f"{DIVIDER}\n"
        f"حالت نمایش منو: {mode}\n"
        "از گزینه‌های زیر استفاده کنید:"
    )


def admin_home_kb() -> InlineKeyboardMarkup:
    glass_label = "⌨️ غیرفعال کردن دکمه شیشه‌ای" if is_glass_mode() else "🪟 فعال کردن دکمه شیشه‌ای"
    kb = [
        [InlineKeyboardButton("🌳 مدیریت منو", callback_data="admtree_0")],
        [InlineKeyboardButton(glass_label, callback_data="admtoggleglass")],
        [InlineKeyboardButton("👋 پیام خوش‌آمدگویی", callback_data="admwelcome")],
        [InlineKeyboardButton("📞 تنظیم متن تماس", callback_data="admcontact")],
        [InlineKeyboardButton("📢 پیام همگانی", callback_data="admbroadcast")],
        [InlineKeyboardButton("💾 بکاپ دیتابیس", callback_data="admbackup")],
        [InlineKeyboardButton("♻️ بازیابی بکاپ", callback_data="admrestore")],
        [InlineKeyboardButton("📊 آمار", callback_data="admstats")],
        [InlineKeyboardButton("⚠️ ریست منو", callback_data="admresetmenu")],
    ]
    return InlineKeyboardMarkup(kb)


def build_tree_kb(parent_id: int) -> InlineKeyboardMarkup:
    buttons = db.get_buttons(parent_id)
    rows = []
    for b in buttons:
        rows.append([InlineKeyboardButton(f"📂 {b['title']}", callback_data=f"admtree_{b['id']}")])
        rows.append([
            InlineKeyboardButton("✏️", callback_data=f"admrenamebtn_{b['id']}"),
            InlineKeyboardButton("🗑️", callback_data=f"admdelbtn_{b['id']}_{parent_id}"),
            InlineKeyboardButton("⬆️", callback_data=f"admmoveup_{b['id']}_{parent_id}"),
            InlineKeyboardButton("⬇️", callback_data=f"admmovedown_{b['id']}_{parent_id}"),
            InlineKeyboardButton("📄", callback_data=f"admfiles_{b['id']}"),
        ])

    rows.append([InlineKeyboardButton("➕ افزودن دکمه/گروه", callback_data=f"admaddbtn_{parent_id}")])
    rows.append([InlineKeyboardButton("📤 افزودن فایل به این بخش", callback_data=f"admaddfile_{parent_id}")])
    rows.append([InlineKeyboardButton("📝 افزودن توضیحات متنی", callback_data=f"admaddtext_{parent_id}")])

    if parent_id != 0:
        parent = db.get_button(parent_id)
        grandparent = parent["parent_id"] if parent else 0
        rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"admtree_{grandparent}")])

    rows.append([InlineKeyboardButton("🏠 پنل مدیریت", callback_data="admhome")])
    return InlineKeyboardMarkup(rows)


def _item_label(item: dict) -> str:
    ftype = item.get("file_type")
    if ftype == "text":
        preview = (item.get("note") or "").strip().replace("\n", " ")
        return f"📝 {preview[:28]}" if preview else "📝 (متن خالی)"
    icon = "🖼️" if ftype == "photo" else "📎"
    label = (item.get("file_name") or item.get("note") or f"فایل #{item['id']}")[:30]
    return f"{icon} {label}"


async def _show_file_list(query, button_id: int):
    items = db.get_catalogs(button_id)
    btn = db.get_button(button_id) if button_id != 0 else None
    title = f"📄 محتوای بخش: {btn['title']}" if btn else "📄 محتوای ریشه"

    rows = []
    if not items:
        rows.append([InlineKeyboardButton("— محتوایی موجود نیست —", callback_data="noop")])
    for item in items:
        label = _item_label(item)
        rows.append([InlineKeyboardButton(f"🗑️ {label}", callback_data=f"admdelfile_{item['id']}_{button_id}")])

    rows.append([InlineKeyboardButton("📤 افزودن فایل", callback_data=f"admaddfile_{button_id}")])
    rows.append([InlineKeyboardButton("📝 افزودن توضیحات متنی", callback_data=f"admaddtext_{button_id}")])
    back_target = btn["parent_id"] if btn else 0
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"admtree_{back_target}")])

    await safe_edit(query, title, reply_markup=InlineKeyboardMarkup(rows))


async def admin_cb_dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await query.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    await query.answer()

    if data == "noop":
        return

    if data == "admhome":
        await query.edit_message_text(admin_home_text(), reply_markup=admin_home_kb(), parse_mode="HTML")
        return

    if data == "admtoggleglass":
        new_value = "off" if is_glass_mode() else "on"
        db.set_setting(GLASS_MODE_KEY, new_value)
        await query.edit_message_text(admin_home_text(), reply_markup=admin_home_kb(), parse_mode="HTML")
        return

    if data == "admstats":
        stats = db.get_stats()
        breakdown = db.get_section_breakdown()
        lines = [
            "📊 <b>آمار ربات</b>",
            DIVIDER,
            f"👥 کاربران: {stats['users']}",
            f"📁 فایل‌ها / متن‌ها: {stats['files']}",
            f"🔘 دکمه‌ها: {stats['buttons']}",
            "",
            "تفکیک بر اساس بخش:",
        ]
        for row in breakdown:
            lines.append(f"• {row['title']}: {row['count']}")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admhome")]])
        await query.edit_message_text("\n".join(lines), reply_markup=kb, parse_mode="HTML")
        return

    if data == "admbackup":
        backup_dir = os.path.join(os.path.dirname(DB_PATH) or ".", "backups")
        os.makedirs(backup_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = os.path.join(backup_dir, f"backup_{ts}.db")
        db.backup_to_file(target)
        with open(target, "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id, document=f, filename=os.path.basename(target)
            )
        return

    if data == "admresetmenu":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ بله، ریست کن", callback_data="admresetmenuyes")],
            [InlineKeyboardButton("❌ انصراف", callback_data="admhome")],
        ])
        await query.edit_message_text(
            "⚠️ این کار تمام دکمه‌ها و محتوای منو را حذف و دسته‌بندی‌های پیش‌فرض را دوباره می‌سازد.\n"
            "تنظیمات و کاربران شما حذف نمی‌شوند.\n\nادامه می‌دهید؟",
            reply_markup=kb,
        )
        return

    if data == "admresetmenuyes":
        db.reset_menu()
        await query.edit_message_text("✅ منو ریست شد.", reply_markup=admin_home_kb())
        return

    if data.startswith("admtree_"):
        parent_id = int(data.split("_")[1])
        parent = db.get_button(parent_id) if parent_id != 0 else None
        title = f"🌳 مدیریت منو — {parent['title']}" if parent else "🌳 مدیریت منو — ریشه"
        await safe_edit(query, title, reply_markup=build_tree_kb(parent_id))
        return

    if data.startswith("admmoveup_") or data.startswith("admmovedown_"):
        parts = data.split("_")
        direction = "up" if parts[0] == "admmoveup" else "down"
        btn_id, parent_id = int(parts[1]), int(parts[2])
        db.move_button(btn_id, direction)
        await query.edit_message_reply_markup(reply_markup=build_tree_kb(parent_id))
        return

    if data.startswith("admfiles_"):
        button_id = int(data.split("_")[1])
        await _show_file_list(query, button_id)
        return

    if data.startswith("admdelfileyes_"):
        parts = data.split("_")
        catalog_id, button_id = int(parts[1]), int(parts[2])
        db.delete_catalog(catalog_id)
        await _show_file_list(query, button_id)
        return

    if data.startswith("admdelfile_"):
        parts = data.split("_")
        catalog_id, button_id = int(parts[1]), int(parts[2])
        item = db.get_catalog_by_id(catalog_id)
        label = _item_label(item) if item else f"#{catalog_id}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"admdelfileyes_{catalog_id}_{button_id}")],
            [InlineKeyboardButton("❌ انصراف", callback_data=f"admfiles_{button_id}")],
        ])
        await query.edit_message_text(f"⚠️ آیا از حذف این مورد مطمئن هستید؟\n\n{label}", reply_markup=kb)
        return

    if data.startswith("admdelbtnyes_"):
        parts = data.split("_")
        btn_id, parent_id = int(parts[1]), int(parts[2])
        db.delete_button(btn_id)
        await query.edit_message_text("✅ حذف شد.", reply_markup=build_tree_kb(parent_id))
        return

    if data.startswith("admdelbtn_"):
        parts = data.split("_")
        btn_id, parent_id = int(parts[1]), int(parts[2])
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"admdelbtnyes_{btn_id}_{parent_id}")],
            [InlineKeyboardButton("❌ انصراف", callback_data=f"admtree_{parent_id}")],
        ])
        await query.edit_message_text(
            "⚠️ این دکمه و تمام زیرمجموعه‌ها و محتوای آن حذف خواهد شد. مطمئن هستید؟",
            reply_markup=kb,
        )
        return


# =========================================================
# CONVERSATION FLOWS
# =========================================================

def _clear_conv_keys(context: ContextTypes.DEFAULT_TYPE):
    for key in (
        "add_parent", "rename_id", "upload_button_id",
        "upload_file_id", "upload_file_name", "upload_file_type",
        "text_button_id",
    ):
        context.user_data.pop(key, None)


async def prompt_add_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parent_id = int(query.data.split("_")[1])
    context.user_data["add_parent"] = parent_id
    await query.edit_message_text("✏️ نام دکمه/گروه جدید را ارسال کنید:\n(برای لغو /cancel)")
    return ADD_BTN


async def save_new_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    parent_id = context.user_data.get("add_parent", 0)
    if not title:
        await update.message.reply_text("نام نمی‌تواند خالی باشد. دوباره ارسال کنید یا /cancel")
        return ADD_BTN
    if db.get_button_by_title_parent(title, parent_id):
        await update.message.reply_text("دکمه‌ای با این نام در این سطح وجود دارد. نام دیگری انتخاب کنید.")
        return ADD_BTN
    db.add_button(title, parent_id)
    _clear_conv_keys(context)
    await update.message.reply_text("✅ دکمه اضافه شد.")
    await update.message.reply_text("🌳 مدیریت منو", reply_markup=build_tree_kb(parent_id))
    return ConversationHandler.END


async def prompt_rename_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    btn_id = int(query.data.split("_")[1])
    context.user_data["rename_id"] = btn_id
    await query.edit_message_text("✏️ نام جدید را ارسال کنید:\n(برای لغو /cancel)")
    return RENAME_BTN


async def save_rename_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_title = update.message.text.strip()
    btn_id = context.user_data.get("rename_id")
    if not new_title or not btn_id:
        await update.message.reply_text("خطا رخ داد. دوباره تلاش کنید.")
        return ConversationHandler.END
    btn = db.get_button(btn_id)
    db.rename_button(btn_id, new_title)
    _clear_conv_keys(context)
    parent_id = btn["parent_id"] if btn else 0
    await update.message.reply_text("✅ نام بروزرسانی شد.")
    await update.message.reply_text("🌳 مدیریت منو", reply_markup=build_tree_kb(parent_id))
    return ConversationHandler.END


async def prompt_add_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    button_id = int(query.data.split("_")[1])
    context.user_data["upload_button_id"] = button_id
    await query.edit_message_text("📤 فایل (عکس یا سند) را ارسال کنید:\n(برای لغو /cancel)")
    return UPLOAD_FILE


async def upload_file_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.document:
        file_id = msg.document.file_id
        file_name = msg.document.file_name
        file_type = "document"
    elif msg.photo:
        file_id = msg.photo[-1].file_id
        file_name = None
        file_type = "photo"
    else:
        await msg.reply_text("لطفاً یک فایل یا عکس ارسال کنید یا /cancel را بزنید.")
        return UPLOAD_FILE

    context.user_data["upload_file_id"] = file_id
    context.user_data["upload_file_name"] = file_name
    context.user_data["upload_file_type"] = file_type
    await msg.reply_text("یک توضیح/عنوان برای این فایل ارسال کنید (برای رد کردن فقط - بفرستید):")
    return UPLOAD_NOTE


async def upload_note_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note_text = update.message.text.strip()
    if note_text == "-":
        note_text = None

    button_id = context.user_data.get("upload_button_id", 0)
    file_id = context.user_data.get("upload_file_id")
    file_name = context.user_data.get("upload_file_name")
    file_type = context.user_data.get("upload_file_type", "document")

    db.add_catalog_file(button_id, file_id, file_name, note_text, file_type)
    _clear_conv_keys(context)
    await update.message.reply_text("✅ فایل اضافه شد.")
    await update.message.reply_text("🌳 مدیریت منو", reply_markup=build_tree_kb(button_id))
    return ConversationHandler.END


async def prompt_add_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    button_id = int(query.data.split("_")[1])
    context.user_data["text_button_id"] = button_id
    await query.edit_message_text(
        "📝 متن/توضیحات را ارسال کنید (می‌تواند چند جمله یا چند خط باشد).\n"
        "این متن هنگام ورود کاربر به این بخش نمایش داده می‌شود.\n"
        "(برای لغو /cancel)"
    )
    return ADD_TEXT


async def save_new_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = update.message.text
    if not content or not content.strip():
        await update.message.reply_text("متن نمی‌تواند خالی باشد. دوباره ارسال کنید یا /cancel")
        return ADD_TEXT

    button_id = context.user_data.get("text_button_id", 0)
    db.add_catalog_file(button_id, "", None, content, "text")
    _clear_conv_keys(context)
    await update.message.reply_text("✅ متن اضافه شد.")
    await update.message.reply_text("🌳 مدیریت منو", reply_markup=build_tree_kb(button_id))
    return ConversationHandler.END


async def prompt_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    current = db.get_setting("contact_text", "تنظیم نشده")
    await query.edit_message_text(f"📞 متن فعلی:\n\n{current}\n\nمتن جدید را ارسال کنید:\n(برای لغو /cancel)")
    return SET_CONTACT


async def set_contact_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.set_setting("contact_text", update.message.text)
    await update.message.reply_text("✅ متن تماس بروزرسانی شد.", reply_markup=admin_home_kb())
    return ConversationHandler.END


async def prompt_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    current = db.get_setting("welcome_text", WELCOME_TEXT_DEFAULT)
    await query.edit_message_text(
        "👋 پیام خوش‌آمدگویی فعلی (نمایش داده‌شده با /start):\n\n"
        f"{current}\n\n"
        "متن جدید را ارسال کنید.\n"
        "نکته: اگر از {name} در متن استفاده کنید، با نام کوچک کاربر جایگزین می‌شود.\n"
        "(برای لغو /cancel)"
    )
    return SET_WELCOME


async def set_welcome_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_text = update.message.text
    if not new_text or not new_text.strip():
        await update.message.reply_text("متن نمی‌تواند خالی باشد. دوباره ارسال کنید یا /cancel")
        return SET_WELCOME

    db.set_setting("welcome_text", new_text)
    preview = new_text.replace("{name}", update.effective_user.first_name or "")
    await update.message.reply_text("✅ پیام خوش‌آمدگویی بروزرسانی شد.\n\nپیش‌نمایش:\n\n" + preview)
    await update.message.reply_text(admin_home_text(), reply_markup=admin_home_kb(), parse_mode="HTML")
    return ConversationHandler.END


async def prompt_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📢 پیام همگانی را ارسال کنید (متن/عکس/فایل):\n(برای لغو /cancel)")
    return BROADCAST


async def broadcast_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = db.get_all_users()
    sent, failed = 0, 0
    msg = update.message
    for uid in users:
        try:
            await msg.copy(chat_id=uid)
            sent += 1
        except Exception:
            failed += 1
    await msg.reply_text(f"✅ ارسال شد به {sent} کاربر. ناموفق: {failed}", reply_markup=admin_home_kb())
    return ConversationHandler.END


async def prompt_restore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "♻️ فایل بکاپ دیتابیس (.db) را به صورت Document ارسال کنید. دیتابیس فعلی جایگزین خواهد شد.\n"
        "(برای لغو /cancel)"
    )
    return RESTORE_DB


async def restore_db_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.document:
        await msg.reply_text("لطفاً فایل دیتابیس را به صورت Document ارسال کنید.")
        return RESTORE_DB

    tg_file = await context.bot.get_file(msg.document.file_id)
    tmp_dir = os.path.join(os.path.dirname(DB_PATH) or ".", "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, f"restore_{msg.document.file_unique_id}.db")
    await tg_file.download_to_drive(tmp_path)

    try:
        db.restore_from_file(tmp_path)
    except Exception as e:
        await msg.reply_text(f"❌ بازیابی ناموفق بود: {e}")
        return ConversationHandler.END
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    await msg.reply_text(
        "✅ دیتابیس بازیابی شد. برای اطمینان از همگام بودن منو /start را بزنید.",
        reply_markup=admin_home_kb(),
    )
    return ConversationHandler.END


# ---------- cancel / fallbacks ----------

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _clear_conv_keys(context)
    parent_id = context.user_data.get("parent_id", 0)
    await update.message.reply_text(
        "لغو شد.",
        reply_markup=build_menu_kb(parent_id, update.effective_user.id),
    )
    return ConversationHandler.END


async def conv_fallback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _clear_conv_keys(context)
    await query.edit_message_text("عملیات لغو شد.", reply_markup=admin_home_kb())
    return ConversationHandler.END


async def conv_fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _clear_conv_keys(context)
    parent_id = context.user_data.get("parent_id", 0)
    await update.message.reply_text(
        "عملیات لغو شد.",
        reply_markup=build_menu_kb(parent_id, update.effective_user.id),
    )
    return ConversationHandler.END


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling update:", exc_info=context.error)


# =========================================================
# MAIN
# =========================================================

def main():
    persistence_path = os.path.join(os.path.dirname(DB_PATH) or ".", "bot_persistence.pickle")
    os.makedirs(os.path.dirname(persistence_path) or ".", exist_ok=True)
    persistence = PicklePersistence(filepath=persistence_path)

    app = Application.builder().token(TOKEN).persistence(persistence).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(prompt_add_btn, pattern=r"^admaddbtn_"),
            CallbackQueryHandler(prompt_rename_btn, pattern=r"^admrenamebtn_"),
            CallbackQueryHandler(prompt_add_file, pattern=r"^admaddfile_"),
            CallbackQueryHandler(prompt_add_text, pattern=r"^admaddtext_"),
            CallbackQueryHandler(prompt_contact, pattern=r"^admcontact$"),
            CallbackQueryHandler(prompt_welcome, pattern=r"^admwelcome$"),
            CallbackQueryHandler(prompt_broadcast, pattern=r"^admbroadcast$"),
            CallbackQueryHandler(prompt_restore, pattern=r"^admrestore$"),
        ],
        states={
            ADD_BTN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_btn)],
            RENAME_BTN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_rename_btn)],
            UPLOAD_FILE: [MessageHandler((filters.Document.ALL | filters.PHOTO) & ~filters.COMMAND, upload_file_receive)],
            UPLOAD_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_note_receive)],
            ADD_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_text)],
            SET_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_contact_receive)],
            SET_WELCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_welcome_receive)],
            BROADCAST: [MessageHandler(~filters.COMMAND, broadcast_receive)],
            RESTORE_DB: [MessageHandler(filters.Document.ALL & ~filters.COMMAND, restore_db_receive)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            CommandHandler("admin", admin_cmd),
            CallbackQueryHandler(conv_fallback_callback),
            MessageHandler(filters.TEXT & ~filters.COMMAND, conv_fallback_text),
        ],
        allow_reentry=True,
        name="admin_conv",
        persistent=True,
    )

    # conversation handler MUST be added before generic handlers
    app.add_handler(conv_handler)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("cancel", cancel))

    # admin inline-panel callbacks
    app.add_handler(CallbackQueryHandler(
        admin_cb_dispatch,
        pattern=r"^(admhome|admtoggleglass|admstats|admbackup|admresetmenu|admresetmenuyes|"
                r"admtree_|admmoveup_|admmovedown_|admfiles_|admdelfile_|admdelfileyes_|"
                r"admdelbtn_|admdelbtnyes_|noop)"
    ))

    # user-facing glass/inline menu callbacks
    app.add_handler(CallbackQueryHandler(
        user_cb_dispatch,
        pattern=r"^(ucat_\d+|uhome|ucontact)$"
    ))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.add_error_handler(error_handler)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
