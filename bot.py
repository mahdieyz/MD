import os
import logging
import html
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    BotCommand,
    MenuButtonCommands,
)
from telegram.constants import ParseMode
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


def parse_admin_ids():
    raw = os.getenv("ADMIN_IDS", "") or os.getenv("ADMIN_ID", "")
    ids = set()
    for part in raw.replace(" ", "").split(","):
        if part.isdigit():
            ids.add(int(part))
    return ids


ADMIN_IDS = parse_admin_ids()

TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN/TOKEN environment variable is not set")

db = Database()

# ---------------------------------------------------------------------------
# Conversation states
# ---------------------------------------------------------------------------
(
    ADD_BTN, ADD_BTN_COLOR, RENAME_BTN, RENAME_BTN_COLOR, ADD_CONTENT,
    SET_CONTACT, SET_WELCOME, SET_MENU_TEXT, SET_SUBMENU_TEXT, SET_PHONE,
    BROADCAST, RESTORE_DB,
) = range(12)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CONTACT_BTN = "🛒 ثبت سفارش / تماس با ما"
ADMIN_BTN = "🔧 پنل مدیریت"
BACK_HOME_BTN = "🔙 بازگشت به منوی اصلی"
SEARCH_BTN = "🔍 جستجو"
PREV_PAGE_BTN = "⬅️ صفحه قبل"
NEXT_PAGE_BTN = "➡️ صفحه بعد"
DIVIDER = "➖➖➖➖➖➖➖➖➖➖"

GLASS_MODE_KEY = "glass_mode"
WELCOME_TEXT_KEY = "welcome_text"
CONTACT_TEXT_KEY = "contact_text"
CONTACT_PHONE_KEY = "contact_phone"
MAIN_MENU_TEXT_KEY = "main_menu_text"
SUBMENU_TEXT_KEY = "submenu_text"

WELCOME_TEXT_DEFAULT = (
    "👋 به ربات ما خوش آمدید!\nاز منوی زیر گزینه مورد نظر خود را انتخاب کنید."
)
MAIN_MENU_TEXT_DEFAULT = "لطفاً یک گزینه را انتخاب کنید:"
CONTACT_TEXT_DEFAULT = "برای ثبت سفارش با شماره زیر تماس بگیرید:\n09120000000"
CONTACT_PHONE_DEFAULT = "09120000000"

SUBMENU_PLACEHOLDER = "\u2063"
CLEAR_SENTINEL = "-"
PAGE_SIZE = 8
MAX_TRACKED_MESSAGES = 500

COLOR_EMOJIS = {
    "red": "🔴", "orange": "🟠", "yellow": "🟡", "green": "🟢",
    "blue": "🔵", "purple": "🟣", "brown": "🟤", "black": "⚫", "white": "⚪",
}
COLOR_PREFIX_CHARS = list(COLOR_EMOJIS.values())


def strip_color(title: str) -> str:
    if title and title[0] in COLOR_PREFIX_CHARS:
        return title[1:].lstrip()
    return title


def _tree_row_label(title: str) -> str:
    return title


def color_picker_kb(callback_prefix: str, cancel_callback: str) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for name, emoji in COLOR_EMOJIS.items():
        row.append(InlineKeyboardButton(emoji, callback_data=f"{callback_prefix}_{name}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("⬜ بدون رنگ", callback_data=f"{callback_prefix}_none")])
    rows.append([InlineKeyboardButton("❌ انصراف", callback_data=cancel_callback)])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_glass_mode() -> bool:
    return db.get_setting(GLASS_MODE_KEY) == "1"


def get_main_menu_text() -> str:
    return db.get_setting(MAIN_MENU_TEXT_KEY) or MAIN_MENU_TEXT_DEFAULT


def get_welcome_text() -> str:
    return db.get_setting(WELCOME_TEXT_KEY) or WELCOME_TEXT_DEFAULT


def get_contact_text() -> str:
    return db.get_setting(CONTACT_TEXT_KEY) or CONTACT_TEXT_DEFAULT


def get_contact_phone() -> str:
    return db.get_setting(CONTACT_PHONE_KEY) or CONTACT_PHONE_DEFAULT


def get_submenu_text() -> str:
    val = db.get_setting(SUBMENU_TEXT_KEY)
    return val if val else SUBMENU_PLACEHOLDER


def sanitize_phone(raw: str) -> str:
    raw = raw.strip()
    digits = ""
    for i, ch in enumerate(raw):
        if ch.isdigit():
            digits += ch
        elif ch == "+" and i == 0:
            digits += ch
    return digits


def paginate(items, page: int, page_size: int = PAGE_SIZE):
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    return items[start:start + page_size], page, total_pages


def contact_inline_kb(back: bool = False) -> InlineKeyboardMarkup:
    phone = get_contact_phone()
    rows = [[InlineKeyboardButton("☎️ تماس مستقیم", url=f"tel:{phone}")]]
    if back:
        rows.append([InlineKeyboardButton(BACK_HOME_BTN, callback_data="uhome")])
    return InlineKeyboardMarkup(rows)


async def safe_edit(query, text=None, reply_markup=None, parse_mode=None):
    try:
        if text is not None:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await query.edit_message_reply_markup(reply_markup=reply_markup)
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            raise


def log_admin_activity(update: Update, action: str, details: str = ""):
    user = update.effective_user
    admin_name = f"@{user.username}" if user.username else (user.full_name or str(user.id))
    db.log_activity(user.id, admin_name, action, details)


# ---------------------------------------------------------------------------
# Message tracking (for /clear)
# ---------------------------------------------------------------------------
def track_message(context: ContextTypes.DEFAULT_TYPE, message_id: int):
    ids = context.chat_data.setdefault("msg_ids", [])
    ids.append(message_id)
    if len(ids) > MAX_TRACKED_MESSAGES:
        del ids[0:len(ids) - MAX_TRACKED_MESSAGES]


async def send_text(context, chat_id, text, reply_markup=None, parse_mode=None):
    msg = await context.bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
    track_message(context, msg.message_id)
    return msg


async def send_photo(context, chat_id, photo, caption=None, reply_markup=None):
    msg = await context.bot.send_photo(chat_id, photo, caption=caption, reply_markup=reply_markup)
    track_message(context, msg.message_id)
    return msg


async def send_document(context, chat_id, document, caption=None, reply_markup=None):
    msg = await context.bot.send_document(chat_id, document, caption=caption, reply_markup=reply_markup)
    track_message(context, msg.message_id)
    return msg


async def reply_text(update: Update, context, text, reply_markup=None, parse_mode=None):
    msg = await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    track_message(context, msg.message_id)
    return msg


async def track_incoming(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_message:
        track_message(context, update.effective_message.message_id)


# ---------------------------------------------------------------------------
# Classic (reply-keyboard) mode
# ---------------------------------------------------------------------------
def build_menu_kb_from_items(page_items, parent_id, user_id, page, total_pages):
    rows = []
    row = []
    for item in page_items:
        row.append(KeyboardButton(item["title"]))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    nav_row = []
    if page > 0:
        nav_row.append(KeyboardButton(PREV_PAGE_BTN))
    if page < total_pages - 1:
        nav_row.append(KeyboardButton(NEXT_PAGE_BTN))
    if nav_row:
        rows.append(nav_row)

    if parent_id == 0:
        rows.append([KeyboardButton(CONTACT_BTN), KeyboardButton(SEARCH_BTN)])
        if is_admin(user_id):
            rows.append([KeyboardButton(ADMIN_BTN)])
    else:
        rows.append([KeyboardButton(BACK_HOME_BTN)])

    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def build_menu_kb(parent_id, user_id, page=0):
    items = db.get_buttons(parent_id)
    page_items, page, total_pages = paginate(items, page)
    return build_menu_kb_from_items(page_items, parent_id, user_id, page, total_pages), page, total_pages


async def _send_section_items(context, chat_id, button_id):
    items = db.get_catalogs(button_id)
    for item in items:
        ftype = item["file_type"]
        note = item["note"] or ""
        if ftype == "photo":
            await send_photo(context, chat_id, item["file_id"], caption=note or None)
        elif ftype == "document":
            await send_document(context, chat_id, item["file_id"], caption=note or None)
        else:
            await send_text(context, chat_id, note or item["file_name"] or "")


async def show_menu(context, chat_id, parent_id, user_id, page=0):
    kb, page, total_pages = build_menu_kb(parent_id, user_id, page)
    context.user_data["menu_page"] = page
    context.user_data["parent_id"] = parent_id

    text = get_main_menu_text() if parent_id == 0 else get_submenu_text()
    if total_pages > 1:
        text = f"{text}\n\n(صفحه {page + 1} از {total_pages})"

    await send_text(context, chat_id, text, reply_markup=kb)


async def enter_button(update: Update, context: ContextTypes.DEFAULT_TYPE, button):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    await _send_section_items(context, chat_id, button["id"])
    context.user_data["parent_id"] = button["id"]
    context.user_data["menu_page"] = 0
    await show_menu(context, chat_id, button["id"], user_id, page=0)


async def do_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query_text: str):
    chat_id = update.effective_chat.id
    buttons, contents = db.search(query_text)
    seen_ids = set()
    rows = []

    for b in buttons:
        if b["id"] in seen_ids:
            continue
        seen_ids.add(b["id"])
        rows.append([InlineKeyboardButton(f"📂 {strip_color(b['title'])}", callback_data=f"ucat_{b['id']}")])

    for c in contents:
        bid = c["button_id"]
        if bid in seen_ids or bid == 0:
            continue
        parent_btn = db.get_button(bid)
        if not parent_btn:
            continue
        seen_ids.add(bid)
        label = c["note"] or c["file_name"] or "مورد"
        rows.append([InlineKeyboardButton(
            f"📄 {label[:30]} ← {strip_color(parent_btn['title'])}", callback_data=f"ucat_{bid}"
        )])

    if not rows:
        await send_text(context, chat_id, "❌ نتیجه‌ای یافت نشد.")
        return

    await send_text(context, chat_id, f"🔍 نتایج جستجو برای «{query_text}»:", reply_markup=InlineKeyboardMarkup(rows))


async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_search"] = True
    await reply_text(update, context, "🔍 عبارت مورد نظر برای جستجو را ارسال کنید:")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if context.user_data.get("awaiting_search"):
        context.user_data["awaiting_search"] = False
        await do_search(update, context, text)
        return

    if is_glass_mode():
        return

    if text == SEARCH_BTN:
        await search_cmd(update, context)
        return

    parent_id = context.user_data.get("parent_id", 0)

    if text == PREV_PAGE_BTN:
        page = context.user_data.get("menu_page", 0)
        await show_menu(context, chat_id, parent_id, user_id, page=max(0, page - 1))
        return

    if text == NEXT_PAGE_BTN:
        page = context.user_data.get("menu_page", 0)
        await show_menu(context, chat_id, parent_id, user_id, page=page + 1)
        return

    if text == BACK_HOME_BTN:
        context.user_data["parent_id"] = 0
        context.user_data["menu_page"] = 0
        await show_menu(context, chat_id, 0, user_id, page=0)
        return

    if text == CONTACT_BTN:
        await send_text(context, chat_id, get_contact_text(), reply_markup=contact_inline_kb())
        return

    if text == ADMIN_BTN:
        if is_admin(user_id):
            await admin_cmd(update, context)
        return

    button = db.get_button_by_title_parent(strip_color(text), parent_id)
    if not button and parent_id != 0:
        button = db.get_button_by_title_parent(strip_color(text), 0)
        if button:
            context.user_data["parent_id"] = 0
            parent_id = 0

    if button:
        await enter_button(update, context, button)
    else:
        await reply_text(update, context, "متوجه نشدم. لطفاً از دکمه‌های منو استفاده کنید.")


async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    context.user_data["parent_id"] = 0
    context.user_data["menu_page"] = 0
    if is_glass_mode():
        await render_user_menu(None, context, 0, 0, user_id, chat_id=chat_id)
    else:
        await show_menu(context, chat_id, 0, user_id, page=0)


async def contact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply_text(update, context, get_contact_text(), reply_markup=contact_inline_kb())


async def clear_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ids = context.chat_data.get("msg_ids", [])
    cmd_msg_id = update.effective_message.message_id
    deleted = 0

    for mid in ids:
        try:
            await context.bot.delete_message(chat_id, mid)
            deleted += 1
        except Exception:
            pass

    try:
        await context.bot.delete_message(chat_id, cmd_msg_id)
    except Exception:
        pass

    context.chat_data["msg_ids"] = []
    notice = await context.bot.send_message(chat_id, f"🧹 {deleted} پیام پاک شد.")
    track_message(context, notice.message_id)


# ---------------------------------------------------------------------------
# Glass (inline) mode
# ---------------------------------------------------------------------------
def build_menu_inline_kb(parent_id, user_id, page=0):
    items = db.get_buttons(parent_id)
    page_items, page, total_pages = paginate(items, page)
    rows = []
    row = []
    for item in page_items:
        row.append(InlineKeyboardButton(item["title"], callback_data=f"ucat_{item['id']}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(PREV_PAGE_BTN, callback_data=f"umenu_{parent_id}_{page - 1}"))
        nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(NEXT_PAGE_BTN, callback_data=f"umenu_{parent_id}_{page + 1}"))
        rows.append(nav_row)

    if parent_id == 0:
        rows.append([
            InlineKeyboardButton(CONTACT_BTN, callback_data="ucontact"),
            InlineKeyboardButton(SEARCH_BTN, callback_data="usearch"),
        ])
        if is_admin(user_id):
            rows.append([InlineKeyboardButton(ADMIN_BTN, callback_data="admhome")])
    else:
        rows.append([InlineKeyboardButton(BACK_HOME_BTN, callback_data="uhome")])

    return InlineKeyboardMarkup(rows), page, total_pages


async def render_user_menu(query, context, parent_id, page, user_id, chat_id=None):
    kb, page, total_pages = build_menu_inline_kb(parent_id, user_id, page)
    text = get_main_menu_text() if parent_id == 0 else get_submenu_text()
    if total_pages > 1:
        text = f"{text}\n\n(صفحه {page + 1} از {total_pages})"

    if query is not None:
        try:
            await safe_edit(query, text=text, reply_markup=kb)
            return
        except Exception:
            chat_id = chat_id or query.message.chat_id

    if chat_id is not None:
        await send_text(context, chat_id, text, reply_markup=kb)


async def user_cb_dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    chat_id = query.message.chat_id

    if data == "uhome":
        context.user_data["parent_id"] = 0
        context.user_data["menu_page"] = 0
        await render_user_menu(query, context, 0, 0, user_id)
        return

    if data == "ucontact":
        await safe_edit(query, text=get_contact_text(), reply_markup=contact_inline_kb(back=True))
        return

    if data == "usearch":
        context.user_data["awaiting_search"] = True
        await send_text(context, chat_id, "🔍 عبارت مورد نظر برای جستجو را ارسال کنید:")
        return

    if data.startswith("umenu_"):
        _, parent_id, page = data.split("_")
        parent_id = int(parent_id)
        page = int(page)
        context.user_data["parent_id"] = parent_id
        context.user_data["menu_page"] = page
        await render_user_menu(query, context, parent_id, page, user_id)
        return

    if data.startswith("ucat_"):
        button_id = int(data.split("_", 1)[1])
        button = db.get_button(button_id)
        if not button:
            await safe_edit(query, text="❌ این بخش دیگر وجود ندارد.", reply_markup=None)
            return
        await _send_section_items(context, chat_id, button_id)
        context.user_data["parent_id"] = button_id
        context.user_data["menu_page"] = 0
        await render_user_menu(query, context, button_id, 0, user_id, chat_id=chat_id)
        return


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name)
    context.user_data["parent_id"] = 0
    context.user_data["menu_page"] = 0

    chat_id = update.effective_chat.id
    await send_text(context, chat_id, get_welcome_text())

    if is_glass_mode():
        await render_user_menu(None, context, 0, 0, user.id, chat_id=chat_id)
    else:
        await show_menu(context, chat_id, 0, user.id, page=0)


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await reply_text(update, context, "⛔ شما به این بخش دسترسی ندارید.")
        return
    await reply_text(update, context, admin_home_text(), reply_markup=admin_home_kb())


def admin_home_text() -> str:
    glass = "فعال ✅" if is_glass_mode() else "غیرفعال ❌"
    return f"🔧 پنل مدیریت\n\nحالت شیشه‌ای (دکمه‌های شناور): {glass}"


def admin_home_kb() -> InlineKeyboardMarkup:
    glass_label = "🪟 غیرفعال‌سازی حالت شیشه‌ای" if is_glass_mode() else "🪟 فعال‌سازی حالت شیشه‌ای"
    rows = [
        [InlineKeyboardButton("🌳 مدیریت منو", callback_data="admtree_0")],
        [InlineKeyboardButton(glass_label, callback_data="admtoggleglass")],
        [InlineKeyboardButton("👋 پیام خوش‌آمدگویی", callback_data="admwelcome")],
        [InlineKeyboardButton("🏠 متن سربرگ منوی اصلی", callback_data="admmenutext")],
        [InlineKeyboardButton("📂 متن سربرگ زیرمنوها", callback_data="admsubmenutext")],
        [InlineKeyboardButton("📞 تنظیم متن تماس", callback_data="admcontact")],
        [InlineKeyboardButton("☎️ شماره تماس مستقیم", callback_data="admphone")],
        [InlineKeyboardButton("📢 پیام همگانی", callback_data="admbroadcast")],
        [InlineKeyboardButton("💾 بکاپ دیتابیس", callback_data="admbackup")],
        [InlineKeyboardButton("♻️ بازیابی بکاپ", callback_data="admrestore")],
        [InlineKeyboardButton("📊 آمار", callback_data="admstats")],
        [InlineKeyboardButton("📜 گزارش فعالیت‌ها", callback_data="admlog")],
        [InlineKeyboardButton("⚠️ ریست منو", callback_data="admresetmenu")],
    ]
    return InlineKeyboardMarkup(rows)


def build_tree_kb(parent_id: int) -> InlineKeyboardMarkup:
    items = db.get_buttons(parent_id)
    rows = []
    for item in items:
        rows.append([InlineKeyboardButton(_tree_row_label(item["title"]), callback_data=f"admtree_{item['id']}")])
        rows.append([
            InlineKeyboardButton("✏️ ویرایش", callback_data=f"admrenamebtn_{item['id']}"),
            InlineKeyboardButton("🎨 رنگ", callback_data=f"admcolor_{item['id']}"),
            InlineKeyboardButton("🗑️ حذف", callback_data=f"admdelbtn_{item['id']}"),
        ])
        rows.append([
            InlineKeyboardButton("⬆️ بالا", callback_data=f"admmoveup_{item['id']}"),
            InlineKeyboardButton("⬇️ پایین", callback_data=f"admmovedown_{item['id']}"),
            InlineKeyboardButton("📄 محتوا", callback_data=f"admfiles_{item['id']}"),
        ])

    rows.append([InlineKeyboardButton("➕ افزودن دکمه/گروه", callback_data=f"admaddbtn_{parent_id}")])
    rows.append([InlineKeyboardButton("➕ افزودن محتوا (متن/عکس/فایل)", callback_data=f"admaddcontent_{parent_id}")])

    if parent_id != 0:
        parent = db.get_button(parent_id)
        grandparent_id = parent["parent_id"] if parent else 0
        rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"admtree_{grandparent_id}")])
    rows.append([InlineKeyboardButton("🏠 پنل مدیریت", callback_data="admhome")])
    return InlineKeyboardMarkup(rows)


def _item_label(item) -> str:
    if item["file_type"] == "photo":
        return f"🖼 {item['note'] or item['file_name'] or 'عکس'}"
    elif item["file_type"] == "document":
        return f"📎 {item['note'] or item['file_name'] or 'فایل'}"
    else:
        return f"📝 {(item['note'] or '')[:40]}"


async def _show_file_list(query, button_id):
    items = db.get_catalogs(button_id)
    rows = []
    for item in items:
        rows.append([
            InlineKeyboardButton(_item_label(item), callback_data="noop"),
            InlineKeyboardButton("🗑️", callback_data=f"admdelfile_{item['id']}"),
        ])
    rows.append([InlineKeyboardButton("➕ افزودن محتوا", callback_data=f"admaddcontent_{button_id}")])
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"admtree_{button_id}")])
    text = "📄 محتوای این بخش:" if items else "📄 این بخش هنوز محتوایی ندارد."
    await safe_edit(query, text=text, reply_markup=InlineKeyboardMarkup(rows))


async def admin_cb_dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "noop":
        await query.answer()
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    await query.answer()

    if data == "admhome":
        await safe_edit(query, text=admin_home_text(), reply_markup=admin_home_kb())
        return

    if data == "admtoggleglass":
        current = is_glass_mode()
        db.set_setting(GLASS_MODE_KEY, "0" if current else "1")
        log_admin_activity(update, "تغییر حالت شیشه‌ای", "فعال" if not current else "غیرفعال")
        await safe_edit(query, text=admin_home_text(), reply_markup=admin_home_kb())
        return

    if data == "admstats":
        stats = db.get_stats()
        growth = db.get_user_growth_stats()
        text = (
            "📊 <b>آمار ربات</b>\n\n"
            f"👤 کاربران کل: {stats['users']}\n"
            f"🆕 کاربر جدید امروز: {growth['today']}\n"
            f"🆕 کاربر جدید (۷ روز اخیر): {growth['week']}\n"
            f"🆕 کاربر جدید (۳۰ روز اخیر): {growth['month']}\n\n"
            f"🔘 تعداد دکمه‌ها: {stats['buttons']}\n"
            f"📁 تعداد محتوا: {stats['catalogs']}\n"
        )
        rows = [[InlineKeyboardButton("🔙 بازگشت", callback_data="admhome")]]
        await safe_edit(query, text=text, reply_markup=InlineKeyboardMarkup(rows), parse_mode=ParseMode.HTML)
        return

    if data == "admlog":
        entries = db.get_recent_activity(20)
        if not entries:
            text = "📜 فعالیتی ثبت نشده است."
        else:
            lines = ["📜 <b>آخرین فعالیت‌های ادمین</b>\n"]
            for e in entries:
                lines.append(
                    f"🕐 {e['created_at']} | {html.escape(e['admin_name'])}\n"
                    f"➡️ {html.escape(e['action'])}"
                    + (f" — {html.escape(e['details'])}" if e["details"] else "")
                )
            text = "\n\n".join(lines)
        rows = [[InlineKeyboardButton("🔙 بازگشت", callback_data="admhome")]]
        await safe_edit(query, text=text, reply_markup=InlineKeyboardMarkup(rows), parse_mode=ParseMode.HTML)
        return

    if data == "admbackup":
        target_path = os.path.join(os.path.dirname(DB_PATH) or ".", f"backup_{int(datetime.now().timestamp())}.db")
        try:
            db.backup_to_file(target_path)
            with open(target_path, "rb") as f:
                await context.bot.send_document(update.effective_chat.id, f)
            log_admin_activity(update, "بکاپ دیتابیس")
        except Exception as e:
            await context.bot.send_message(update.effective_chat.id, f"❌ خطا در تهیه بکاپ: {e}")
        return

    if data == "admresetmenu":
        rows = [
            [InlineKeyboardButton("✅ بله، ریست کن", callback_data="admresetmenuyes")],
            [InlineKeyboardButton("❌ انصراف", callback_data="admhome")],
        ]
        await safe_edit(query, text="⚠️ آیا مطمئن هستید؟ تمام منو و محتوا حذف خواهد شد.", reply_markup=InlineKeyboardMarkup(rows))
        return

    if data == "admresetmenuyes":
        db.reset_menu()
        log_admin_activity(update, "ریست منو")
        await safe_edit(query, text="✅ منو ریست شد.", reply_markup=admin_home_kb())
        return

    if data.startswith("admtree_"):
        parent_id = int(data.split("_", 1)[1])
        await safe_edit(query, text="🌳 مدیریت منو:", reply_markup=build_tree_kb(parent_id))
        return

    if data.startswith("admmoveup_"):
        button_id = int(data.split("_", 1)[1])
        button = db.get_button(button_id)
        db.move_button(button_id, -1)
        await safe_edit(query, text="🌳 مدیریت منو:", reply_markup=build_tree_kb(button["parent_id"]))
        return

    if data.startswith("admmovedown_"):
        button_id = int(data.split("_", 1)[1])
        button = db.get_button(button_id)
        db.move_button(button_id, 1)
        await safe_edit(query, text="🌳 مدیریت منو:", reply_markup=build_tree_kb(button["parent_id"]))
        return

    if data.startswith("admfiles_"):
        button_id = int(data.split("_", 1)[1])
        await _show_file_list(query, button_id)
        return

    if data.startswith("admdelfileyes_"):
        item_id = int(data.split("_", 1)[1])
        item = db.get_catalog_by_id(item_id)
        if item:
            db.delete_catalog(item_id)
            log_admin_activity(update, "حذف محتوا", _item_label(item))
            await _show_file_list(query, item["button_id"])
        return

    if data.startswith("admdelfile_"):
        item_id = int(data.split("_", 1)[1])
        rows = [
            [InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"admdelfileyes_{item_id}")],
            [InlineKeyboardButton("❌ انصراف", callback_data="noop")],
        ]
        await safe_edit(query, text="⚠️ این مورد حذف شود؟", reply_markup=InlineKeyboardMarkup(rows))
        return

    if data.startswith("admdelbtnyes_"):
        button_id = int(data.split("_", 1)[1])
        button = db.get_button(button_id)
        if button:
            db.delete_button(button_id)
            log_admin_activity(update, "حذف دکمه", button["title"])
            await safe_edit(query, text="🌳 مدیریت منو:", reply_markup=build_tree_kb(button["parent_id"]))
        return

    if data.startswith("admdelbtn_"):
        button_id = int(data.split("_", 1)[1])
        rows = [
            [InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"admdelbtnyes_{button_id}")],
            [InlineKeyboardButton("❌ انصراف", callback_data="noop")],
        ]
        await safe_edit(query, text="⚠️ این دکمه و تمام زیرمجموعه‌های آن حذف شود؟", reply_markup=InlineKeyboardMarkup(rows))
        return

    if data.startswith("admcolorset_"):
        _, button_id, color_name = data.split("_", 2)
        button_id = int(button_id)
        button = db.get_button(button_id)
        base_title = strip_color(button["title"])
        new_title = base_title if color_name == "none" else f"{COLOR_EMOJIS[color_name]} {base_title}"
        db.rename_button(button_id, new_title)
        log_admin_activity(update, "تغییر رنگ دکمه", new_title)
        await safe_edit(query, text="🌳 مدیریت منو:", reply_markup=build_tree_kb(button["parent_id"]))
        return

    if data.startswith("admcolor_"):
        button_id = int(data.split("_", 1)[1])
        await safe_edit(
            query,
            text="🎨 رنگ مورد نظر را انتخاب کنید:",
            reply_markup=color_picker_kb(f"admcolorset_{button_id}", "noop"),
        )
        return


# ---------------------------------------------------------------------------
# Conversation flows
# ---------------------------------------------------------------------------
def _clear_conv_keys(context: ContextTypes.DEFAULT_TYPE):
    for key in ("target_parent_id", "rename_button_id", "pending_title",
                "content_button_id", "content_added_count", "content_status_msg_id"):
        context.user_data.pop(key, None)


async def prompt_add_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parent_id = int(query.data.split("_", 1)[1])
    context.user_data["target_parent_id"] = parent_id
    await safe_edit(query, text="✏️ عنوان دکمه/گروه جدید را ارسال کنید:", reply_markup=None)
    return ADD_BTN


async def save_new_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    if not title:
        await reply_text(update, context, "❌ عنوان نمی‌تواند خالی باشد. دوباره ارسال کنید:")
        return ADD_BTN
    context.user_data["pending_title"] = title
    await reply_text(update, context, "🎨 رنگی برای این دکمه انتخاب کنید:",
                      reply_markup=color_picker_kb("admnewcolor", "admnewcolorcancel"))
    return ADD_BTN_COLOR


async def save_new_btn_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    parent_id = context.user_data.get("target_parent_id", 0)
    title = context.user_data.get("pending_title", "")

    if data == "admnewcolorcancel":
        _clear_conv_keys(context)
        await safe_edit(query, text="❌ لغو شد.")
        return ConversationHandler.END

    color_name = data.split("_", 1)[1]
    final_title = title if color_name == "none" else f"{COLOR_EMOJIS[color_name]} {title}"

    db.add_button(parent_id, final_title)
    log_admin_activity(update, "افزودن دکمه", final_title)
    _clear_conv_keys(context)

    await safe_edit(query, text=f"✅ دکمه «{final_title}» اضافه شد.\n\n🌳 مدیریت منو:", reply_markup=build_tree_kb(parent_id))
    return ConversationHandler.END


async def prompt_rename_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    button_id = int(query.data.split("_", 1)[1])
    context.user_data["rename_button_id"] = button_id
    button = db.get_button(button_id)
    await safe_edit(query, text=f"✏️ عنوان جدید برای «{strip_color(button['title'])}» را ارسال کنید:", reply_markup=None)
    return RENAME_BTN


async def save_rename_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    if not title:
        await reply_text(update, context, "❌ عنوان نمی‌تواند خالی باشد. دوباره ارسال کنید:")
        return RENAME_BTN
    context.user_data["pending_title"] = title
    await reply_text(update, context, "🎨 رنگی برای این دکمه انتخاب کنید:",
                      reply_markup=color_picker_kb("admrencolor", "admrencolorcancel"))
    return RENAME_BTN_COLOR


async def save_rename_btn_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    button_id = context.user_data.get("rename_button_id")
    title = context.user_data.get("pending_title", "")
    button = db.get_button(button_id)

    if data == "admrencolorcancel":
        _clear_conv_keys(context)
        await safe_edit(query, text="❌ لغو شد.")
        return ConversationHandler.END

    color_name = data.split("_", 1)[1]
    final_title = title if color_name == "none" else f"{COLOR_EMOJIS[color_name]} {title}"

    db.rename_button(button_id, final_title)
    log_admin_activity(update, "ویرایش دکمه", final_title)
    parent_id = button["parent_id"] if button else 0
    _clear_conv_keys(context)

    await safe_edit(query, text=f"✅ دکمه به «{final_title}» تغییر یافت.\n\n🌳 مدیریت منو:", reply_markup=build_tree_kb(parent_id))
    return ConversationHandler.END


async def prompt_add_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    button_id = int(query.data.split("_", 1)[1])
    context.user_data["content_button_id"] = button_id
    context.user_data["content_added_count"] = 0
    context.user_data["content_status_msg_id"] = None

    rows = [[InlineKeyboardButton("✅ پایان افزودن", callback_data="admfinishcontent")]]
    await safe_edit(
        query,
        text=(
            "📤 حالا می‌توانید عکس، فایل یا متن ارسال کنید.\n"
            "می‌توانید چند مورد پشت سر هم بفرستید (حتی چند عکس با هم).\n"
            "وقتی تمام شد، روی «پایان افزودن» بزنید."
        ),
        reply_markup=InlineKeyboardMarkup(rows),
    )
    return ADD_CONTENT


async def _update_content_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = context.user_data.get("content_added_count", 0)
    chat_id = update.effective_chat.id
    status_msg_id = context.user_data.get("content_status_msg_id")
    text = f"✅ تا کنون {count} مورد اضافه شد.\nبرای پایان، «پایان افزودن» را بزنید یا مورد بعدی را ارسال کنید."
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ پایان افزودن", callback_data="admfinishcontent")]])

    if status_msg_id:
        try:
            await context.bot.edit_message_text(text, chat_id=chat_id, message_id=status_msg_id, reply_markup=kb)
            return
        except Exception:
            pass

    msg = await context.bot.send_message(chat_id, text, reply_markup=kb)
    track_message(context, msg.message_id)
    context.user_data["content_status_msg_id"] = msg.message_id


async def add_content_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    button_id = context.user_data.get("content_button_id")
    if button_id is None:
        await reply_text(update, context, "❌ خطا، دوباره تلاش کنید.")
        return ConversationHandler.END

    message = update.message

    if message.photo:
        file_id = message.photo[-1].file_id
        note = message.caption or ""
        db.add_catalog_file(button_id, file_id, None, note, "photo")
    elif message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
        note = message.caption or ""
        db.add_catalog_file(button_id, file_id, file_name, note, "document")
    elif message.text:
        db.add_catalog_file(button_id, None, None, message.text.strip(), "text")
    else:
        await reply_text(update, context, "❌ نوع پیام پشتیبانی نمی‌شود. عکس، فایل یا متن ارسال کنید.")
        return ADD_CONTENT

    context.user_data["content_added_count"] = context.user_data.get("content_added_count", 0) + 1
    await _update_content_status(update, context)
    return ADD_CONTENT


async def finish_add_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    button_id = context.user_data.get("content_button_id") or 0
    count = context.user_data.get("content_added_count", 0)

    log_admin_activity(update, "افزودن محتوا", f"{count} مورد")
    _clear_conv_keys(context)

    await safe_edit(query, text=f"✅ {count} مورد اضافه شد.\n\n🌳 مدیریت منو:", reply_markup=build_tree_kb(button_id))
    return ConversationHandler.END


async def prompt_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await safe_edit(query, text=f"📞 متن فعلی:\n\n{get_contact_text()}\n\nمتن جدید را ارسال کنید:", reply_markup=None)
    return SET_CONTACT


async def set_contact_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    db.set_setting(CONTACT_TEXT_KEY, text)
    log_admin_activity(update, "ویرایش متن تماس")
    await reply_text(update, context, "✅ متن تماس به‌روزرسانی شد.", reply_markup=admin_home_kb())
    return ConversationHandler.END


async def prompt_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await safe_edit(
        query,
        text=f"☎️ شماره فعلی: {get_contact_phone()}\n\nشماره جدید را فقط با رقم (و در صورت نیاز + ابتدایی) ارسال کنید:",
        reply_markup=None,
    )
    return SET_PHONE


async def set_phone_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = sanitize_phone(update.message.text)
    if not phone:
        await reply_text(update, context, "❌ شماره نامعتبر است. فقط رقم (و + اختیاری در ابتدا) ارسال کنید:")
        return SET_PHONE
    db.set_setting(CONTACT_PHONE_KEY, phone)
    log_admin_activity(update, "ویرایش شماره تماس مستقیم", phone)
    await reply_text(update, context, f"✅ شماره تماس مستقیم به {phone} تغییر یافت.", reply_markup=admin_home_kb())
    return ConversationHandler.END


async def prompt_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await safe_edit(query, text=f"👋 پیام فعلی:\n\n{get_welcome_text()}\n\nپیام جدید را ارسال کنید:", reply_markup=None)
    return SET_WELCOME


async def set_welcome_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    db.set_setting(WELCOME_TEXT_KEY, text)
    log_admin_activity(update, "ویرایش پیام خوش‌آمدگویی")
    await reply_text(update, context, f"✅ پیام خوش‌آمدگویی به‌روزرسانی شد.\n\nپیش‌نمایش:\n\n{text}", reply_markup=admin_home_kb())
    return ConversationHandler.END


async def prompt_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await safe_edit(query, text=f"🏠 متن فعلی:\n\n{get_main_menu_text()}\n\nمتن جدید را ارسال کنید:", reply_markup=None)
    return SET_MENU_TEXT


async def set_menu_text_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    db.set_setting(MAIN_MENU_TEXT_KEY, text)
    log_admin_activity(update, "ویرایش متن سربرگ منوی اصلی")
    await reply_text(update, context, "✅ متن سربرگ منوی اصلی به‌روزرسانی شد.", reply_markup=admin_home_kb())
    return ConversationHandler.END


async def prompt_submenu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    current = db.get_setting(SUBMENU_TEXT_KEY) or "(نامرئی - فقط دکمه)"
    await safe_edit(
        query,
        text=f"📂 متن فعلی:\n\n{current}\n\nمتن جدید را ارسال کنید، یا برای حذف (بازگشت به حالت نامرئی) «-» ارسال کنید:",
        reply_markup=None,
    )
    return SET_SUBMENU_TEXT


async def set_submenu_text_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == CLEAR_SENTINEL:
        db.set_setting(SUBMENU_TEXT_KEY, "")
        log_admin_activity(update, "ویرایش متن سربرگ زیرمنوها", "(حذف شد)")
        await reply_text(update, context, "✅ متن سربرگ زیرمنوها حذف شد (حالت نامرئی).", reply_markup=admin_home_kb())
    else:
        db.set_setting(SUBMENU_TEXT_KEY, text)
        log_admin_activity(update, "ویرایش متن سربرگ زیرمنوها")
        await reply_text(update, context, "✅ متن سربرگ زیرمنوها به‌روزرسانی شد.", reply_markup=admin_home_kb())
    return ConversationHandler.END


async def prompt_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await safe_edit(query, text="📢 پیام همگانی را ارسال کنید (برای همه کاربران فوروارد می‌شود):", reply_markup=None)
    return BROADCAST


async def broadcast_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = db.get_all_users()
    sent = 0
    failed = 0
    for u in users:
        try:
            await context.bot.copy_message(
                chat_id=u["user_id"],
                from_chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
            )
            sent += 1
        except Exception:
            failed += 1

    log_admin_activity(update, "پیام همگانی", f"ارسال موفق: {sent} | ناموفق: {failed}")
    await reply_text(update, context, f"✅ پیام همگانی ارسال شد.\nموفق: {sent}\nناموفق: {failed}", reply_markup=admin_home_kb())
    return ConversationHandler.END


async def prompt_restore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await safe_edit(query, text="♻️ فایل بکاپ (.db) را ارسال کنید:", reply_markup=None)
    return RESTORE_DB


async def restore_db_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document:
        await reply_text(update, context, "❌ لطفاً یک فایل ارسال کنید.")
        return RESTORE_DB

    file = await document.get_file()
    tmp_path = os.path.join(os.path.dirname(DB_PATH) or ".", "restore_tmp.db")
    await file.download_to_drive(tmp_path)

    try:
        db.restore_from_file(tmp_path)
        log_admin_activity(update, "بازیابی دیتابیس")
        await reply_text(update, context, "✅ دیتابیس با موفقیت بازیابی شد.", reply_markup=admin_home_kb())
    except Exception as e:
        await reply_text(update, context, f"❌ خطا در بازیابی: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Generic handlers
# ---------------------------------------------------------------------------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _clear_conv_keys(context)
    await reply_text(update, context, "❌ عملیات لغو شد.")
    return ConversationHandler.END


async def conv_fallback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _clear_conv_keys(context)
    await safe_edit(query, text=admin_home_text(), reply_markup=admin_home_kb())
    return ConversationHandler.END


async def conv_fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _clear_conv_keys(context)
    await reply_text(update, context, "❌ عملیات لغو شد.")
    return ConversationHandler.END


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling an update:", exc_info=context.error)


# ---------------------------------------------------------------------------
# Startup: command list + menu button (the fix)
# ---------------------------------------------------------------------------
async def post_init(application: Application):
    commands = [
        BotCommand("start", "🏁 شروع / بازگشت به اول"),
        BotCommand("menu", "🏠 رفتن به منوی اصلی"),
        BotCommand("search", "🔍 جستجو در منو"),
        BotCommand("contact", "📞 اطلاعات تماس"),
        BotCommand("clear", "🧹 پاک کردن پیام‌های این چت"),
        BotCommand("admin", "🔧 پنل مدیریت (ادمین)"),
        BotCommand("cancel", "❌ لغو عملیات جاری"),
    ]
    await application.bot.set_my_commands(commands)
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    persistence_path = os.path.join(os.path.dirname(DB_PATH) or ".", "bot_persistence.pickle")
    persistence = PicklePersistence(filepath=persistence_path)

    app = (
        Application.builder()
        .token(TOKEN)
        .persistence(persistence)
        .post_init(post_init)
        .build()
    )

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(prompt_add_btn, pattern=r"^admaddbtn_"),
            CallbackQueryHandler(prompt_rename_btn, pattern=r"^admrenamebtn_"),
            CallbackQueryHandler(prompt_add_content, pattern=r"^admaddcontent_"),
            CallbackQueryHandler(prompt_contact, pattern=r"^admcontact$"),
            CallbackQueryHandler(prompt_phone, pattern=r"^admphone$"),
            CallbackQueryHandler(prompt_welcome, pattern=r"^admwelcome$"),
            CallbackQueryHandler(prompt_menu_text, pattern=r"^admmenutext$"),
            CallbackQueryHandler(prompt_submenu_text, pattern=r"^admsubmenutext$"),
            CallbackQueryHandler(prompt_broadcast, pattern=r"^admbroadcast$"),
            CallbackQueryHandler(prompt_restore, pattern=r"^admrestore$"),
        ],
        states={
            ADD_BTN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_btn)],
            ADD_BTN_COLOR: [CallbackQueryHandler(save_new_btn_color, pattern=r"^admnewcolor")],
            RENAME_BTN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_rename_btn)],
            RENAME_BTN_COLOR: [CallbackQueryHandler(save_rename_btn_color, pattern=r"^admrencolor")],
            ADD_CONTENT: [
                CallbackQueryHandler(finish_add_content, pattern=r"^admfinishcontent$"),
                MessageHandler((filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, add_content_receive),
            ],
            SET_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_contact_receive)],
            SET_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_phone_receive)],
            SET_WELCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_welcome_receive)],
            SET_MENU_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_menu_text_receive)],
            SET_SUBMENU_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_submenu_text_receive)],
            BROADCAST: [MessageHandler(~filters.COMMAND, broadcast_receive)],
            RESTORE_DB: [MessageHandler(filters.Document.ALL & ~filters.COMMAND, restore_db_receive)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            CommandHandler("admin", admin_cmd),
            CallbackQueryHandler(conv_fallback_callback),
            MessageHandler(filters.ALL, conv_fallback_text),
        ],
        allow_reentry=True,
        name="admin_conv",
        persistent=True,
    )

    app.add_handler(MessageHandler(filters.ALL, track_incoming), group=-1)
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CommandHandler("contact", contact_cmd))
    app.add_handler(CommandHandler("clear", clear_chat))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(CallbackQueryHandler(
        admin_cb_dispatch,
        pattern=r"^(admhome|admtoggleglass|admstats|admlog|admbackup|admresetmenu|admresetmenuyes|admtree_|admmoveup_|admmovedown_|admfiles_|admdelfile_|admdelfileyes_|admdelbtn_|admdelbtnyes_|admcolor_|admcolorset_|noop)"
    ))
    app.add_handler(CallbackQueryHandler(
        user_cb_dispatch,
        pattern=r"^(ucat_\d+|uhome|ucontact|usearch|umenu_\d+_\d+)$"
    ))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
