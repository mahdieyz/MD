import os
import html
import logging
import tempfile
from datetime import datetime

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BotCommand,
)
from telegram.constants import ParseMode
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


def parse_admin_ids(raw: str):
    ids = set()
    if not raw:
        return ids
    raw = raw.strip().strip("[]")
    for part in raw.replace("'", "").replace('"', "").split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


ADMIN_IDS = parse_admin_ids(os.getenv("ADMIN_IDS", ""))

TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN/TOKEN environment variable is not set")

db = Database()

# Conversation states
(
    ADD_BTN,
    ADD_BTN_COLOR,
    RENAME_BTN,
    RENAME_BTN_COLOR,
    ADD_CONTENT,
    SET_CONTACT,
    SET_WELCOME,
    SET_MENU_TEXT,
    SET_SUBMENU_TEXT,
    SET_PHONE,
    BROADCAST,
    RESTORE_DB,
) = range(12)

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
    "سلام {name} عزیز 👋\n\n"
    "خوش آمدید.\n"
    "از منوی زیر گزینه موردنظر خود را انتخاب کنید."
)
MAIN_MENU_TEXT_DEFAULT = "لطفاً یک گزینه را انتخاب کنید:"
CONTACT_TEXT_DEFAULT = "برای ثبت سفارش با شماره زیر تماس بگیرید:\n09120000000"
CONTACT_PHONE_DEFAULT = "09120000000"

SUBMENU_PLACEHOLDER = "\u2063"
CLEAR_SENTINEL = "-"
PAGE_SIZE = 8

# Color tagging for buttons (Telegram has no real button-color API, so we
# fake it with a leading colored-circle emoji in the button title).
COLOR_EMOJIS = {
    "red": "🔴",
    "orange": "🟠",
    "yellow": "🟡",
    "green": "🟢",
    "blue": "🔵",
    "purple": "🟣",
    "brown": "🟤",
    "black": "⚫",
    "white": "⚪",
    "none": "",
}
COLOR_PREFIX_CHARS = ["🔴", "🟠", "🟡", "🟢", "🔵", "🟣", "🟤", "⚫", "⚪"]

MAX_TRACKED_MESSAGES = 500


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_glass_mode() -> bool:
    return db.get_setting(GLASS_MODE_KEY, "off") == "on"


def get_main_menu_text() -> str:
    return db.get_setting(MAIN_MENU_TEXT_KEY, MAIN_MENU_TEXT_DEFAULT)


def get_welcome_text() -> str:
    return db.get_setting(WELCOME_TEXT_KEY, WELCOME_TEXT_DEFAULT)


def get_contact_text() -> str:
    return db.get_setting(CONTACT_TEXT_KEY, CONTACT_TEXT_DEFAULT)


def get_contact_phone() -> str:
    return db.get_setting(CONTACT_PHONE_KEY, CONTACT_PHONE_DEFAULT)


def get_submenu_text() -> str:
    val = db.get_setting(SUBMENU_TEXT_KEY, "")
    if not val or not val.strip():
        return SUBMENU_PLACEHOLDER
    return val


def sanitize_phone(raw: str) -> str:
    return "".join(ch for ch in raw if ch.isdigit() or ch == "+")


def strip_color(title: str) -> str:
    t = title.strip()
    for emoji in COLOR_PREFIX_CHARS:
        if t.startswith(emoji):
            return t[len(emoji):].strip()
    return t


def _tree_row_label(title: str) -> str:
    for emoji in COLOR_PREFIX_CHARS:
        if title.startswith(emoji):
            return title
    return f"📂 {title}"


def color_picker_kb(callback_prefix: str, cancel_callback: str) -> InlineKeyboardMarkup:
    colors = [(k, v) for k, v in COLOR_EMOJIS.items() if k != "none"]
    rows = []
    row = []
    for key, emoji in colors:
        row.append(InlineKeyboardButton(emoji, callback_data=f"{callback_prefix}_{key}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🚫 بدون رنگ", callback_data=f"{callback_prefix}_none")])
    rows.append([InlineKeyboardButton("❌ انصراف", callback_data=cancel_callback)])
    return InlineKeyboardMarkup(rows)


def paginate(items, page, page_size=PAGE_SIZE):
    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    return items[start:start + page_size], page, total_pages


def contact_inline_kb(back=False):
    phone = get_contact_phone()
    rows = []
    if phone:
        rows.append([InlineKeyboardButton("☎️ تماس مستقیم", url=f"tel:{phone}")])
    if back:
        rows.append([InlineKeyboardButton(BACK_HOME_BTN, callback_data="uhome")])
    if not rows:
        return None
    return InlineKeyboardMarkup(rows)


async def safe_edit(query, text, reply_markup=None, parse_mode=None):
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except BadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


def log_admin_activity(update, action, details=""):
    user = update.effective_user
    if user.username:
        admin_name = f"@{user.username}"
    else:
        admin_name = user.full_name or str(user.id)
    db.log_activity(user.id, admin_name, action, details)


# ============================================================
# Message tracking (for /clear) + tracked send helpers
# ============================================================

async def track_message(context, message):
    if message is None:
        return
    ids = context.chat_data.setdefault("msg_ids", [])
    ids.append(message.message_id)
    if len(ids) > MAX_TRACKED_MESSAGES:
        del ids[: len(ids) - MAX_TRACKED_MESSAGES]


async def send_text(context, chat_id, text, **kwargs):
    msg = await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
    await track_message(context, msg)
    return msg


async def send_photo(context, chat_id, photo, **kwargs):
    msg = await context.bot.send_photo(chat_id=chat_id, photo=photo, **kwargs)
    await track_message(context, msg)
    return msg


async def send_document(context, chat_id, document, **kwargs):
    msg = await context.bot.send_document(chat_id=chat_id, document=document, **kwargs)
    await track_message(context, msg)
    return msg


async def reply_text(update, context, text, **kwargs):
    msg = await update.message.reply_text(text, **kwargs)
    await track_message(context, msg)
    return msg


async def track_incoming(update, context):
    if update.message:
        await track_message(context, update.message)


# ============================================================
# Reply-keyboard (classic) mode
# ============================================================

def build_menu_kb_from_items(page_items, parent_id, user_id, page, total_pages):
    rows = []
    row = []
    for b in page_items:
        row.append(KeyboardButton(b["title"]))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(KeyboardButton(PREV_PAGE_BTN))
        if page < total_pages - 1:
            nav.append(KeyboardButton(NEXT_PAGE_BTN))
        if nav:
            rows.append(nav)

    if parent_id == 0:
        rows.append([KeyboardButton(CONTACT_BTN), KeyboardButton(SEARCH_BTN)])
        if is_admin(user_id):
            rows.append([KeyboardButton(ADMIN_BTN)])
    else:
        rows.append([KeyboardButton(BACK_HOME_BTN)])

    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def build_menu_kb(parent_id: int, user_id: int, page: int = 0) -> ReplyKeyboardMarkup:
    all_buttons = db.get_buttons(parent_id)
    page_items, page, total_pages = paginate(all_buttons, page)
    return build_menu_kb_from_items(page_items, parent_id, user_id, page, total_pages)


async def _send_section_items(context, chat_id, items):
    for item in items:
        ftype = item["file_type"]
        if ftype == "text":
            await send_text(context, chat_id, item["note"] or "")
        elif ftype == "photo":
            await send_photo(context, chat_id, item["file_id"], caption=item["note"] or None)
        else:
            await send_document(context, chat_id, item["file_id"], caption=item["note"] or None)


async def show_menu(context, chat_id, parent_id, user_id, page=0):
    all_buttons = db.get_buttons(parent_id)
    page_items, page, total_pages = paginate(all_buttons, page)
    context.user_data["menu_page"] = page

    kb = build_menu_kb_from_items(page_items, parent_id, user_id, page, total_pages)
    base_text = get_main_menu_text() if parent_id == 0 else get_submenu_text()

    if total_pages > 1:
        page_info = f"📄 صفحه {page + 1} از {total_pages}"
        text = page_info if base_text == SUBMENU_PLACEHOLDER else f"{base_text}\n\n{page_info}"
    else:
        text = base_text

    await send_text(context, chat_id, text, reply_markup=kb)


async def enter_button(update: Update, context: ContextTypes.DEFAULT_TYPE, button):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    context.user_data["parent_id"] = button["id"]

    items = db.get_catalogs(button["id"])
    if items:
        await _send_section_items(context, chat_id, items)

    await show_menu(context, chat_id, button["id"], user_id, 0)


async def do_search(update, context, query_text):
    chat_id = update.effective_chat.id
    if not query_text:
        await reply_text(update, context, "⚠️ عبارت جستجو نباید خالی باشد.")
        return

    buttons, contents = db.search(query_text)
    seen_ids = set()
    rows = []

    for b in buttons[:15]:
        if b["id"] in seen_ids:
            continue
        seen_ids.add(b["id"])
        rows.append([InlineKeyboardButton(f"📂 {b['title']}", callback_data=f"ucat_{b['id']}")])

    for c in contents[:15]:
        bid = c["button_id"]
        if bid == 0 or bid in seen_ids:
            continue
        seen_ids.add(bid)
        parent = db.get_button(bid)
        parent_title = parent["title"] if parent else "بخش"
        preview = (c["note"] or c["file_name"] or "").strip().replace("\n", " ")
        if len(preview) > 30:
            preview = preview[:30] + "…"
        rows.append([InlineKeyboardButton(f"📄 {parent_title} › {preview}", callback_data=f"ucat_{bid}")])

    if not rows:
        await reply_text(update, context, f"🔍 برای «{query_text}» نتیجه‌ای یافت نشد.")
        return

    kb = InlineKeyboardMarkup(rows)
    await reply_text(update, context, f"🔍 نتایج جستجو برای «{query_text}»:", reply_markup=kb)


async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_search"] = True
    await reply_text(update, context, "🔍 کلمه موردنظر برای جستجو را ارسال کنید:")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if context.user_data.get("awaiting_search"):
        context.user_data["awaiting_search"] = False
        await do_search(update, context, text.strip())
        return

    if is_glass_mode():
        if text == ADMIN_BTN and is_admin(user_id):
            await admin_cmd(update, context)
            return
        await reply_text(
            update, context,
            "لطفاً از دکمه‌های شیشه‌ای بالا استفاده کنید. برای شروع دوباره /start را بزنید."
        )
        return

    if text == SEARCH_BTN:
        context.user_data["awaiting_search"] = True
        await reply_text(update, context, "🔍 کلمه موردنظر برای جستجو را ارسال کنید:")
        return

    if text == PREV_PAGE_BTN:
        parent_id = context.user_data.get("parent_id", 0)
        page = max(0, context.user_data.get("menu_page", 0) - 1)
        await show_menu(context, chat_id, parent_id, user_id, page)
        return

    if text == NEXT_PAGE_BTN:
        parent_id = context.user_data.get("parent_id", 0)
        page = context.user_data.get("menu_page", 0) + 1
        await show_menu(context, chat_id, parent_id, user_id, page)
        return

    if text == BACK_HOME_BTN:
        context.user_data["parent_id"] = 0
        await show_menu(context, chat_id, 0, user_id, 0)
        return

    if text == CONTACT_BTN:
        await reply_text(update, context, get_contact_text(), reply_markup=contact_inline_kb())
        return

    if text == ADMIN_BTN:
        if is_admin(user_id):
            await admin_cmd(update, context)
        return

    parent_id = context.user_data.get("parent_id", 0)
    button = db.get_button_by_title_parent(text, parent_id)

    if not button and parent_id != 0:
        button = db.get_button_by_title_parent(text, 0)
        if button:
            context.user_data["parent_id"] = 0

    if not button:
        context.user_data["parent_id"] = 0
        await show_menu(context, chat_id, 0, user_id, 0)
        return

    await enter_button(update, context, button)


async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    context.user_data["parent_id"] = 0
    if is_glass_mode():
        kb = build_menu_inline_kb(0, user_id)
        await send_text(context, chat_id, get_main_menu_text(), reply_markup=kb)
    else:
        await show_menu(context, chat_id, 0, user_id, 0)


async def contact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await send_text(context, chat_id, get_contact_text(), reply_markup=contact_inline_kb())


async def clear_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ids = context.chat_data.get("msg_ids", [])
    deleted = 0
    for mid in list(ids):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
            deleted += 1
        except Exception:
            pass
    context.chat_data["msg_ids"] = []

    try:
        await update.message.delete()
    except Exception:
        pass

    notice = await context.bot.send_message(chat_id=chat_id, text=f"🧹 چت پاک شد. ({deleted} پیام حذف شد)")
    await track_message(context, notice)


# ============================================================
# Glass / inline mode
# ============================================================

def build_menu_inline_kb(parent_id: int, user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    all_buttons = db.get_buttons(parent_id)
    page_items, page, total_pages = paginate(all_buttons, page)

    rows = []
    row = []
    for b in page_items:
        row.append(InlineKeyboardButton(b["title"], callback_data=f"ucat_{b['id']}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"umenu_{parent_id}_{page - 1}"))
        nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("➡️ بعدی", callback_data=f"umenu_{parent_id}_{page + 1}"))
        rows.append(nav)

    if parent_id == 0:
        rows.append([InlineKeyboardButton(CONTACT_BTN, callback_data="ucontact")])
        rows.append([InlineKeyboardButton(SEARCH_BTN, callback_data="usearch")])
        if is_admin(user_id):
            rows.append([InlineKeyboardButton(ADMIN_BTN, callback_data="admhome")])
    else:
        rows.append([InlineKeyboardButton(BACK_HOME_BTN, callback_data="uhome")])

    return InlineKeyboardMarkup(rows)


async def render_user_menu(query, context, parent_id, page, user_id, chat_id=None):
    all_buttons = db.get_buttons(parent_id)
    page_items, clamped_page, total_pages = paginate(all_buttons, page)
    kb = build_menu_inline_kb(parent_id, user_id, clamped_page)
    base_text = get_main_menu_text() if parent_id == 0 else get_submenu_text()

    if total_pages > 1:
        page_info = f"📄 صفحه {clamped_page + 1} از {total_pages}"
        text = page_info if base_text == SUBMENU_PLACEHOLDER else f"{base_text}\n\n{page_info}"
    else:
        text = base_text

    try:
        await safe_edit(query, text, reply_markup=kb)
    except BadRequest:
        if chat_id is not None:
            await send_text(context, chat_id, text, reply_markup=kb)


async def user_cb_dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if data == "uhome":
        context.user_data["parent_id"] = 0
        await render_user_menu(query, context, 0, 0, user_id, chat_id=chat_id)
        return

    if data == "ucontact":
        kb = contact_inline_kb(back=True)
        await safe_edit(query, get_contact_text(), reply_markup=kb)
        return

    if data == "usearch":
        context.user_data["awaiting_search"] = True
        await send_text(context, chat_id, "🔍 کلمه موردنظر برای جستجو را ارسال کنید:")
        return

    if data.startswith("umenu_"):
        parts = data.split("_")
        parent_id = int(parts[1])
        page = int(parts[2])
        context.user_data["parent_id"] = parent_id
        await render_user_menu(query, context, parent_id, page, user_id, chat_id=chat_id)
        return

    if data.startswith("ucat_"):
        button_id = int(data.split("_", 1)[1])
        button = db.get_button(button_id)
        if not button:
            context.user_data["parent_id"] = 0
            await render_user_menu(query, context, 0, 0, user_id, chat_id=chat_id)
            return

        context.user_data["parent_id"] = button_id

        items = db.get_catalogs(button_id)
        if items:
            await _send_section_items(context, chat_id, items)

        await render_user_menu(query, context, button_id, 0, user_id, chat_id=chat_id)
        return


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name)
    context.user_data["parent_id"] = 0
    context.user_data["menu_page"] = 0

    name = user.first_name or "کاربر"
    welcome = get_welcome_text().format(name=name)
    chat_id = update.effective_chat.id

    if is_glass_mode():
        await send_text(context, chat_id, welcome)
        kb = build_menu_inline_kb(0, user.id)
        await send_text(context, chat_id, get_main_menu_text(), reply_markup=kb)
    else:
        kb = build_menu_kb(0, user.id)
        await send_text(context, chat_id, welcome, reply_markup=kb)


# ============================================================
# Admin panel
# ============================================================

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        if update.message:
            await reply_text(update, context, "⛔ شما دسترسی ادمین ندارید.")
        return

    _clear_conv_keys(context)
    text = admin_home_text()
    kb = admin_home_kb()

    if update.callback_query:
        await safe_edit(update.callback_query, text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        await reply_text(update, context, text, reply_markup=kb, parse_mode=ParseMode.HTML)


def admin_home_text() -> str:
    glass = "🟢 فعال" if is_glass_mode() else "🔴 غیرفعال"
    return (
        "🔧 <b>پنل مدیریت</b>\n"
        f"{DIVIDER}\n"
        f"حالت دکمه شیشه‌ای: {glass}\n"
        f"{DIVIDER}\n"
        "یک گزینه را انتخاب کنید:"
    )


def admin_home_kb() -> InlineKeyboardMarkup:
    glass_label = "🔳 خاموش کردن دکمه شیشه‌ای" if is_glass_mode() else "🔲 روشن کردن دکمه شیشه‌ای"
    rows = [
        [InlineKeyboardButton("🌳 مدیریت منو", callback_data="admtree_0")],
        [InlineKeyboardButton(glass_label, callback_data="admtoggleglass")],
        [InlineKeyboardButton("👋 پیام خوش‌آمدگویی", callback_data="admwelcome")],
        [InlineKeyboardButton("🏠 متن سربرگ منوی اصلی", callback_data="admmenutext")],
        [InlineKeyboardButton("📂 متن سربرگ زیرمنوها", callback_data="admsubmenutext")],
        [InlineKeyboardButton("☎️ شماره تماس مستقیم", callback_data="admphone")],
        [InlineKeyboardButton("📞 تنظیم متن تماس", callback_data="admcontact")],
        [InlineKeyboardButton("📢 پیام همگانی", callback_data="admbroadcast")],
        [InlineKeyboardButton("📜 گزارش فعالیت‌ها", callback_data="admlog")],
        [InlineKeyboardButton("💾 بکاپ دیتابیس", callback_data="admbackup")],
        [InlineKeyboardButton("♻️ بازیابی بکاپ", callback_data="admrestore")],
        [InlineKeyboardButton("📊 آمار", callback_data="admstats")],
        [InlineKeyboardButton("⚠️ ریست منو", callback_data="admresetmenu")],
    ]
    return InlineKeyboardMarkup(rows)


def build_tree_kb(parent_id: int) -> InlineKeyboardMarkup:
    buttons = db.get_buttons(parent_id)
    rows = []
    for b in buttons:
        rows.append([InlineKeyboardButton(_tree_row_label(b["title"]), callback_data=f"admtree_{b['id']}")])
        rows.append([
            InlineKeyboardButton("✏️ ویرایش", callback_data=f"admrenamebtn_{b['id']}"),
            InlineKeyboardButton("🎨 رنگ", callback_data=f"admcolor_{b['id']}"),
            InlineKeyboardButton("🗑️ حذف", callback_data=f"admdelbtn_{b['id']}"),
        ])
        rows.append([
            InlineKeyboardButton("⬆️ بالا", callback_data=f"admmoveup_{b['id']}"),
            InlineKeyboardButton("⬇️ پایین", callback_data=f"admmovedown_{b['id']}"),
            InlineKeyboardButton("📄 محتوا", callback_data=f"admfiles_{b['id']}"),
        ])

    rows.append([InlineKeyboardButton("➕ افزودن دکمه/گروه", callback_data=f"admaddbtn_{parent_id}")])
    rows.append([InlineKeyboardButton("➕ افزودن محتوا (متن/عکس/فایل)", callback_data=f"admaddcontent_{parent_id}")])

    if parent_id != 0:
        parent = db.get_button(parent_id)
        back_to = parent["parent_id"] if parent else 0
        rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"admtree_{back_to}")])

    rows.append([InlineKeyboardButton("🏠 پنل مدیریت", callback_data="admhome")])
    return InlineKeyboardMarkup(rows)


def _item_label(item) -> str:
    if item["file_type"] == "text":
        preview = (item["note"] or "").strip().replace("\n", " ")
        if len(preview) > 25:
            preview = preview[:25] + "…"
        return f"📝 {preview}"
    elif item["file_type"] == "photo":
        return f"🖼️ {item['file_name'] or 'عکس'}"
    else:
        return f"📎 {item['file_name'] or 'فایل'}"


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

    text = "📄 محتوای این بخش:" if items else "این بخش هنوز محتوایی ندارد."
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(rows))


async def admin_cb_dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "noop":
        await query.answer()
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.answer("⛔ دسترسی ندارید", show_alert=True)
        return
    await query.answer()

    if data == "admhome":
        _clear_conv_keys(context)
        await safe_edit(query, admin_home_text(), reply_markup=admin_home_kb(), parse_mode=ParseMode.HTML)
        return

    if data == "admtoggleglass":
        new_val = "off" if is_glass_mode() else "on"
        db.set_setting(GLASS_MODE_KEY, new_val)
        log_admin_activity(update, "تغییر حالت دکمه شیشه‌ای", new_val)
        await safe_edit(query, admin_home_text(), reply_markup=admin_home_kb(), parse_mode=ParseMode.HTML)
        return

    if data == "admstats":
        stats = db.get_stats()
        growth = db.get_user_growth_stats()
        breakdown = db.get_section_breakdown()
        lines = [
            "📊 <b>آمار ربات</b>",
            DIVIDER,
            f"👤 تعداد کل کاربران: {stats.get('users', 0)}",
            f"🆕 کاربران جدید امروز: {growth.get('today', 0)}",
            f"📅 کاربران جدید (۷ روز اخیر): {growth.get('week', 0)}",
            f"🗓️ کاربران جدید (۳۰ روز اخیر): {growth.get('month', 0)}",
            DIVIDER,
            f"🗂️ تعداد دکمه‌ها: {stats.get('buttons', 0)}",
            f"📁 تعداد محتوا: {stats.get('catalogs', 0)}",
            DIVIDER,
        ]
        for row in breakdown:
            lines.append(f"• {html.escape(str(row['title']))}: {row['count']}")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admhome")]])
        await safe_edit(query, "\n".join(lines), reply_markup=kb, parse_mode=ParseMode.HTML)
        return

    if data == "admlog":
        entries = db.get_recent_activity(20)
        if not entries:
            lines = ["📜 گزارش فعالیت‌ها", DIVIDER, "هنوز فعالیتی ثبت نشده است."]
        else:
            lines = ["📜 گزارش فعالیت‌ها (۲۰ مورد اخیر)", DIVIDER]
            for e in entries:
                admin_label = e["admin_name"] or str(e["admin_id"])
                detail = f" - {e['details']}" if e["details"] else ""
                lines.append(f"🕒 {e['created_at']} | {admin_label}: {e['action']}{detail}")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admhome")]])
        await safe_edit(query, "\n".join(lines), reply_markup=kb)
        return

    if data == "admbackup":
        target = os.path.join(
            os.path.dirname(DB_PATH) or ".",
            f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
        )
        db.backup_to_file(target)
        with open(target, "rb") as f:
            await send_document(context, query.message.chat_id, f, filename=os.path.basename(target))
        await query.answer("✅ بکاپ ارسال شد")
        return

    if data == "admresetmenu":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ بله، ریست شود", callback_data="admresetmenuyes")],
            [InlineKeyboardButton("❌ انصراف", callback_data="admhome")],
        ])
        await safe_edit(query, "⚠️ آیا مطمئن هستید؟ تمام منو و محتوا حذف و به حالت پیش‌فرض بازمی‌گردد.", reply_markup=kb)
        return

    if data == "admresetmenuyes":
        db.reset_menu()
        log_admin_activity(update, "ریست منو")
        await safe_edit(query, "✅ منو ریست شد.", reply_markup=admin_home_kb())
        return

    if data.startswith("admtree_"):
        parent_id = int(data.split("_", 1)[1])
        await safe_edit(query, f"🌳 مدیریت منو\n{DIVIDER}", reply_markup=build_tree_kb(parent_id))
        return

    if data.startswith("admmoveup_"):
        button_id = int(data.split("_", 1)[1])
        db.move_button(button_id, "up")
        button = db.get_button(button_id)
        await safe_edit(query, f"🌳 مدیریت منو\n{DIVIDER}", reply_markup=build_tree_kb(button["parent_id"]))
        return

    if data.startswith("admmovedown_"):
        button_id = int(data.split("_", 1)[1])
        db.move_button(button_id, "down")
        button = db.get_button(button_id)
        await safe_edit(query, f"🌳 مدیریت منو\n{DIVIDER}", reply_markup=build_tree_kb(button["parent_id"]))
        return

    if data.startswith("admfiles_"):
        button_id = int(data.split("_", 1)[1])
        await _show_file_list(query, button_id)
        return

    if data.startswith("admdelfileyes_"):
        item_id = int(data.split("_", 1)[1])
        item = db.get_catalog_by_id(item_id)
        button_id = item["button_id"] if item else 0
        if item:
            log_admin_activity(update, "حذف محتوا", _item_label(item))
        db.delete_catalog(item_id)
        await _show_file_list(query, button_id)
        return

    if data.startswith("admdelfile_"):
        item_id = int(data.split("_", 1)[1])
        item = db.get_catalog_by_id(item_id)
        if not item:
            await query.answer("یافت نشد", show_alert=True)
            return
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ بله، حذف شود", callback_data=f"admdelfileyes_{item_id}")],
            [InlineKeyboardButton("❌ انصراف", callback_data=f"admfiles_{item['button_id']}")],
        ])
        await safe_edit(query, f"⚠️ آیا از حذف مورد زیر مطمئن هستید؟\n\n{_item_label(item)}", reply_markup=kb)
        return

    if data.startswith("admdelbtnyes_"):
        button_id = int(data.split("_", 1)[1])
        button = db.get_button(button_id)
        parent_id = button["parent_id"] if button else 0
        if button:
            log_admin_activity(update, "حذف دکمه", strip_color(button["title"]))
        db.delete_button(button_id)
        await safe_edit(query, f"🌳 مدیریت منو\n{DIVIDER}", reply_markup=build_tree_kb(parent_id))
        return

    if data.startswith("admdelbtn_"):
        button_id = int(data.split("_", 1)[1])
        button = db.get_button(button_id)
        if not button:
            await query.answer("یافت نشد", show_alert=True)
            return
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ بله، حذف شود", callback_data=f"admdelbtnyes_{button_id}")],
            [InlineKeyboardButton("❌ انصراف", callback_data=f"admtree_{button['parent_id']}")],
        ])
        await safe_edit(query, f"⚠️ آیا از حذف «{button['title']}» و تمام زیرمجموعه‌های آن مطمئن هستید؟", reply_markup=kb)
        return

    if data.startswith("admcolorset_"):
        rest = data[len("admcolorset_"):]
        button_id_str, color_key = rest.rsplit("_", 1)
        button_id = int(button_id_str)
        button = db.get_button(button_id)
        if not button:
            await query.answer("یافت نشد", show_alert=True)
            return
        base_title = strip_color(button["title"])
        emoji = COLOR_EMOJIS.get(color_key, "")
        new_title = f"{emoji} {base_title}".strip() if emoji else base_title
        db.rename_button(button_id, new_title)
        log_admin_activity(update, "تغییر رنگ دکمه", new_title)
        await safe_edit(query, f"🌳 مدیریت منو\n{DIVIDER}", reply_markup=build_tree_kb(button["parent_id"]))
        return

    if data.startswith("admcolor_"):
        button_id = int(data.split("_", 1)[1])
        button = db.get_button(button_id)
        if not button:
            await query.answer("یافت نشد", show_alert=True)
            return
        kb = color_picker_kb(f"admcolorset_{button_id}", f"admtree_{button['parent_id']}")
        await safe_edit(query, f"🎨 انتخاب رنگ برای «{strip_color(button['title'])}»:", reply_markup=kb)
        return


# ============================================================
# Conversation flows
# ============================================================

def _clear_conv_keys(context):
    for key in (
        "target_parent_id",
        "rename_button_id",
        "pending_title",
        "content_button_id",
        "content_added_count",
        "content_status_msg_id",
    ):
        context.user_data.pop(key, None)


async def prompt_add_btn(update, context):
    query = update.callback_query
    await query.answer()
    parent_id = int(query.data.split("_", 1)[1])
    context.user_data["target_parent_id"] = parent_id
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data=f"admtree_{parent_id}")]])
    await safe_edit(query, "✏️ نام دکمه/گروه جدید را ارسال کنید:", reply_markup=kb)
    return ADD_BTN


async def save_new_btn(update, context):
    title = update.message.text.strip()
    if not title:
        await reply_text(update, context, "⚠️ نام نباید خالی باشد. دوباره ارسال کنید:")
        return ADD_BTN
    context.user_data["pending_title"] = title
    parent_id = context.user_data.get("target_parent_id", 0)
    kb = color_picker_kb("newcolor", f"admtree_{parent_id}")
    await reply_text(update, context, "🎨 رنگ دکمه را انتخاب کنید:", reply_markup=kb)
    return ADD_BTN_COLOR


async def save_new_btn_color(update, context):
    query = update.callback_query
    await query.answer()
    color_key = query.data.split("_", 1)[1]
    emoji = COLOR_EMOJIS.get(color_key, "")
    title = context.user_data.get("pending_title", "دکمه")
    parent_id = context.user_data.get("target_parent_id", 0)
    full_title = f"{emoji} {title}".strip() if emoji else title
    db.add_button(full_title, parent_id)
    log_admin_activity(update, "افزودن دکمه", full_title)
    _clear_conv_keys(context)
    await safe_edit(query, f"✅ «{full_title}» اضافه شد.", reply_markup=build_tree_kb(parent_id))
    return ConversationHandler.END


async def prompt_rename_btn(update, context):
    query = update.callback_query
    await query.answer()
    button_id = int(query.data.split("_", 1)[1])
    context.user_data["rename_button_id"] = button_id
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data=f"admtree_{button_id}")]])
    await safe_edit(query, "✏️ نام جدید را ارسال کنید:", reply_markup=kb)
    return RENAME_BTN


async def save_rename_btn(update, context):
    title = update.message.text.strip()
    button_id = context.user_data.get("rename_button_id")
    if not title or not button_id:
        await reply_text(update, context, "⚠️ خطا، دوباره تلاش کنید.")
        return ConversationHandler.END
    context.user_data["pending_title"] = title
    button = db.get_button(button_id)
    parent_id = button["parent_id"] if button else 0
    kb = color_picker_kb("renamecolor", f"admtree_{parent_id}")
    await reply_text(update, context, "🎨 رنگ دکمه را انتخاب کنید:", reply_markup=kb)
    return RENAME_BTN_COLOR


async def save_rename_btn_color(update, context):
    query = update.callback_query
    await query.answer()
    color_key = query.data.split("_", 1)[1]
    emoji = COLOR_EMOJIS.get(color_key, "")
    title = context.user_data.get("pending_title", "")
    button_id = context.user_data.get("rename_button_id")
    full_title = f"{emoji} {title}".strip() if emoji else title
    db.rename_button(button_id, full_title)
    log_admin_activity(update, "ویرایش دکمه", full_title)
    button = db.get_button(button_id)
    parent_id = button["parent_id"] if button else 0
    _clear_conv_keys(context)
    await safe_edit(query, "✅ تغییر نام/رنگ انجام شد.", reply_markup=build_tree_kb(parent_id))
    return ConversationHandler.END


# ---- Bulk content add (text / photo / document, unlimited items) ----

async def prompt_add_content(update, context):
    query = update.callback_query
    await query.answer()
    button_id = int(query.data.split("_", 1)[1])
    context.user_data["content_button_id"] = button_id
    context.user_data["content_added_count"] = 0
    context.user_data["content_status_msg_id"] = None
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ پایان افزودن", callback_data="admfinishcontent")]])
    await safe_edit(
        query,
        "➕ حالا می‌توانید هر تعداد عکس، فایل یا متن که می‌خواهید را پشت سر هم ارسال کنید.\n"
        "هرکدام بلافاصله ذخیره می‌شود. وقتی تمام شد دکمه پایان را بزنید:",
        reply_markup=kb,
    )
    return ADD_CONTENT


async def _update_content_status(update, context):
    chat_id = update.effective_chat.id
    count = context.user_data.get("content_added_count", 0)
    text = f"✅ تا کنون {count} مورد اضافه شد.\nمی‌توانید مورد بعدی را ارسال کنید یا پایان دهید."
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ پایان افزودن", callback_data="admfinishcontent")]])
    status_msg_id = context.user_data.get("content_status_msg_id")

    if status_msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=status_msg_id, text=text, reply_markup=kb
            )
            return
        except BadRequest:
            pass

    msg = await reply_text(update, context, text, reply_markup=kb)
    context.user_data["content_status_msg_id"] = msg.message_id


async def add_content_receive(update, context):
    msg = update.message
    button_id = context.user_data.get("content_button_id")
    if not button_id and button_id != 0:
        await reply_text(update, context, "⚠️ خطا، دوباره از منو شروع کنید.")
        return ConversationHandler.END

    if msg.photo:
        file_id = msg.photo[-1].file_id
        note = msg.caption or ""
        db.add_catalog_file(button_id, file_id, "عکس", note, "photo")
    elif msg.document:
        file_id = msg.document.file_id
        file_name = msg.document.file_name or "فایل"
        note = msg.caption or ""
        db.add_catalog_file(button_id, file_id, file_name, note, "document")
    elif msg.text and msg.text.strip():
        db.add_catalog_file(button_id, "", "متن", msg.text.strip(), "text")
    else:
        await reply_text(update, context, "⚠️ این نوع پیام پشتیبانی نمی‌شود. عکس، فایل یا متن ارسال کنید.")
        return ADD_CONTENT

    context.user_data["content_added_count"] = context.user_data.get("content_added_count", 0) + 1
    await _update_content_status(update, context)
    return ADD_CONTENT


async def finish_add_content(update, context):
    query = update.callback_query
    await query.answer()
    button_id = context.user_data.get("content_button_id", 0)
    count = context.user_data.get("content_added_count", 0)
    log_admin_activity(update, "افزودن محتوا", f"{count} مورد")
    _clear_conv_keys(context)
    await safe_edit(query, f"✅ افزودن محتوا پایان یافت. ({count} مورد اضافه شد)", reply_markup=build_tree_kb(button_id))
    return ConversationHandler.END


# ---- Simple text/phone settings ----

async def prompt_contact(update, context):
    query = update.callback_query
    await query.answer()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="admhome")]])
    await safe_edit(
        query,
        f"📞 متن فعلی:\n\n{get_contact_text()}\n\n{DIVIDER}\nمتن جدید را ارسال کنید:",
        reply_markup=kb,
    )
    return SET_CONTACT


async def set_contact_receive(update, context):
    text = update.message.text.strip()
    db.set_setting(CONTACT_TEXT_KEY, text)
    log_admin_activity(update, "ویرایش متن تماس")
    await reply_text(update, context, "✅ متن تماس بروزرسانی شد.", reply_markup=admin_home_kb())
    return ConversationHandler.END


async def prompt_phone(update, context):
    query = update.callback_query
    await query.answer()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="admhome")]])
    await safe_edit(
        query,
        f"☎️ شماره فعلی برای تماس مستقیم:\n\n{get_contact_phone()}\n\n{DIVIDER}\n"
        "شماره جدید را ارسال کنید (فقط عدد، مثال: 09120000000):",
        reply_markup=kb,
    )
    return SET_PHONE


async def set_phone_receive(update, context):
    raw = update.message.text.strip()
    phone = sanitize_phone(raw)
    if not phone:
        await reply_text(update, context, "⚠️ شماره نامعتبر است. دوباره ارسال کنید:")
        return SET_PHONE
    db.set_setting(CONTACT_PHONE_KEY, phone)
    log_admin_activity(update, "ویرایش شماره تماس مستقیم", phone)
    await reply_text(update, context, f"✅ شماره تماس به‌روزرسانی شد: {phone}", reply_markup=admin_home_kb())
    return ConversationHandler.END


async def prompt_welcome(update, context):
    query = update.callback_query
    await query.answer()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="admhome")]])
    await safe_edit(
        query,
        f"👋 متن فعلی:\n\n{get_welcome_text()}\n\n{DIVIDER}\n"
        "متن جدید را ارسال کنید (می‌توانید از {name} برای درج نام کاربر استفاده کنید):",
        reply_markup=kb,
    )
    return SET_WELCOME


async def set_welcome_receive(update, context):
    text = update.message.text.strip()
    db.set_setting(WELCOME_TEXT_KEY, text)
    log_admin_activity(update, "ویرایش پیام خوش‌آمدگویی")
    preview = text.format(name=update.effective_user.first_name or "کاربر")
    await reply_text(
        update, context,
        f"✅ متن خوش‌آمدگویی بروزرسانی شد.\n\n{DIVIDER}\nپیش‌نمایش:\n{preview}",
        reply_markup=admin_home_kb(),
    )
    return ConversationHandler.END


async def prompt_menu_text(update, context):
    query = update.callback_query
    await query.answer()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="admhome")]])
    await safe_edit(
        query,
        f"🏠 متن فعلی سربرگ منوی اصلی:\n\n{get_main_menu_text()}\n\n{DIVIDER}\nمتن جدید را ارسال کنید:",
        reply_markup=kb,
    )
    return SET_MENU_TEXT


async def set_menu_text_receive(update, context):
    text = update.message.text.strip()
    db.set_setting(MAIN_MENU_TEXT_KEY, text)
    log_admin_activity(update, "ویرایش متن سربرگ منوی اصلی")
    await reply_text(update, context, "✅ متن سربرگ منوی اصلی بروزرسانی شد.", reply_markup=admin_home_kb())
    return ConversationHandler.END


async def prompt_submenu_text(update, context):
    query = update.callback_query
    await query.answer()
    current = db.get_setting(SUBMENU_TEXT_KEY, "")
    current_display = current if current.strip() else "(خالی - فقط دکمه‌ها نمایش داده می‌شود)"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="admhome")]])
    await safe_edit(
        query,
        f"📂 متن فعلی سربرگ زیرمنوها:\n\n{current_display}\n\n{DIVIDER}\n"
        "متن جدید را ارسال کنید.\n"
        "برای حذف کامل متن (نمایش فقط دکمه‌ها بدون پیام) علامت - را ارسال کنید:",
        reply_markup=kb,
    )
    return SET_SUBMENU_TEXT


async def set_submenu_text_receive(update, context):
    text = update.message.text.strip()
    if text == CLEAR_SENTINEL:
        db.set_setting(SUBMENU_TEXT_KEY, "")
        log_admin_activity(update, "ویرایش متن سربرگ زیرمنوها", "(حذف شد)")
        await reply_text(
            update, context,
            "✅ متن سربرگ زیرمنوها حذف شد. از این پس فقط دکمه‌ها نمایش داده می‌شوند.",
            reply_markup=admin_home_kb(),
        )
    else:
        db.set_setting(SUBMENU_TEXT_KEY, text)
        log_admin_activity(update, "ویرایش متن سربرگ زیرمنوها")
        await reply_text(update, context, "✅ متن سربرگ زیرمنوها بروزرسانی شد.", reply_markup=admin_home_kb())
    return ConversationHandler.END


async def prompt_broadcast(update, context):
    query = update.callback_query
    await query.answer()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="admhome")]])
    await safe_edit(query, "📢 پیام همگانی را ارسال کنید (متن/عکس/فایل):", reply_markup=kb)
    return BROADCAST


async def broadcast_receive(update, context):
    msg = update.message
    users = db.get_all_users()
    sent, failed = 0, 0
    for u in users:
        try:
            await msg.copy(chat_id=u["user_id"])
            sent += 1
        except Exception:
            failed += 1
    log_admin_activity(update, "ارسال پیام همگانی", f"{sent} موفق / {failed} ناموفق")
    await reply_text(update, context, f"✅ ارسال شد به {sent} کاربر.\n❌ ناموفق: {failed}", reply_markup=admin_home_kb())
    return ConversationHandler.END


async def prompt_restore(update, context):
    query = update.callback_query
    await query.answer()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="admhome")]])
    await safe_edit(query, "♻️ فایل بکاپ دیتابیس (.db) را ارسال کنید:", reply_markup=kb)
    return RESTORE_DB


async def restore_db_receive(update, context):
    doc = update.message.document
    if not doc:
        await reply_text(update, context, "⚠️ لطفاً یک فایل ارسال کنید.")
        return RESTORE_DB

    file = await doc.get_file()
    tmp_path = os.path.join(tempfile.gettempdir(), f"restore_{doc.file_unique_id}.db")
    await file.download_to_drive(tmp_path)

    try:
        db.restore_from_file(tmp_path)
    except Exception as e:
        await reply_text(update, context, f"❌ بازیابی ناموفق بود: {e}")
        return ConversationHandler.END
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    log_admin_activity(update, "بازیابی دیتابیس")
    await reply_text(update, context, "✅ بازیابی با موفقیت انجام شد.", reply_markup=admin_home_kb())
    return ConversationHandler.END


async def cancel(update, context):
    _clear_conv_keys(context)
    if update.message:
        await reply_text(update, context, "❌ عملیات لغو شد.")
    return ConversationHandler.END


async def conv_fallback_callback(update, context):
    query = update.callback_query
    await query.answer()
    _clear_conv_keys(context)
    if is_admin(update.effective_user.id):
        await safe_edit(query, admin_home_text(), reply_markup=admin_home_kb(), parse_mode=ParseMode.HTML)
    return ConversationHandler.END


async def conv_fallback_text(update, context):
    _clear_conv_keys(context)
    await reply_text(update, context, "❌ عملیات قبلی لغو شد.")
    return ConversationHandler.END


async def error_handler(update, context):
    logger.error("Exception while handling an update:", exc_info=context.error)


async def post_init(application: Application):
    await application.bot.set_my_commands([
        BotCommand("start", "شروع / بازگشت به منوی اصلی"),
        BotCommand("menu", "نمایش منوی اصلی"),
        BotCommand("search", "جستجو در منو و محتوا"),
        BotCommand("contact", "تماس با ما"),
        BotCommand("clear", "پاک کردن چت"),
        BotCommand("admin", "پنل مدیریت (ادمین)"),
        BotCommand("cancel", "لغو عملیات جاری"),
    ])


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
            ADD_BTN_COLOR: [CallbackQueryHandler(save_new_btn_color, pattern=r"^newcolor_")],
            RENAME_BTN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_rename_btn)],
            RENAME_BTN_COLOR: [CallbackQueryHandler(save_rename_btn_color, pattern=r"^renamecolor_")],
            ADD_CONTENT: [
                CallbackQueryHandler(finish_add_content, pattern=r"^admfinishcontent$"),
                MessageHandler(
                    (filters.TEXT & ~filters.COMMAND) | filters.PHOTO | filters.Document.ALL,
                    add_content_receive,
                ),
            ],
            SET_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_contact_receive)],
            SET_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_phone_receive)],
            SET_WELCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_welcome_receive)],
            SET_MENU_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_menu_text_receive)],
            SET_SUBMENU_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_submenu_text_receive)],
            BROADCAST: [MessageHandler(~filters.COMMAND, broadcast_receive)],
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
        pattern=r"^(admhome|admtoggleglass|admstats|admlog|admbackup|admresetmenu|admresetmenuyes|admtree_|admmoveup_|admmovedown_|admfiles_|admdelfile_|admdelfileyes_|admdelbtn_|admdelbtnyes_|admcolor_|admcolorset_|noop)",
    ))
    app.add_handler(CallbackQueryHandler(
        user_cb_dispatch,
        pattern=r"^(ucat_\d+|uhome|ucontact|usearch|umenu_\d+_\d+)$",
    ))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
