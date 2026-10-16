import os
import re
import asyncio
import logging

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputFile,
)
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)
import database

logger = logging.getLogger(__name__)


def parse_admin_ids():
    raw = os.getenv("ADMIN_IDS", "") or ""
    ids = []
    for part in re.split(r"[,\s\[\]'\"]+", raw):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids


ADMIN_IDS = parse_admin_ids()

(
    STATE_EDIT_WELCOME,
    STATE_EDIT_CONTACT,
    STATE_BROADCAST,
    STATE_ADD_BTN,
    STATE_ADD_CATALOG_FILE,
    STATE_ADD_CATALOG_CAPTION,
) = range(6)

MAIN_MENU_TEXTS = {
    "📦 محصولات و قیمت‌ها",
    "📞 تماس با ما",
    "🔧 پنل مدیریت",
}


def is_admin(user_id):
    if not user_id:
        return False
    return int(user_id) in ADMIN_IDS


async def maybe_handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    text = update.message.text if update.message else None
    if text in MAIN_MENU_TEXTS:
        context.user_data.clear()
        await handle_text(update, context)
        return True
    return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user = update.effective_user
    if user:
        try:
            database.add_user(user.id, user.username, user.full_name)
        except Exception as e:
            logger.error("Error adding user: %s", e)

    welcome_text = database.get_setting("welcome_text", "به ربات توان سازه خوش آمدید.")

    keyboard = [
        [KeyboardButton("📦 محصولات و قیمت‌ها")],
        [KeyboardButton("📞 تماس با ما")],
    ]
    if user and is_admin(user.id):
        keyboard.append([KeyboardButton("🔧 پنل مدیریت")])

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.effective_message.reply_text(welcome_text, reply_markup=reply_markup)
    return ConversationHandler.END


async def admin_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user = update.effective_user
    if not user:
        return ConversationHandler.END

    if is_admin(user.id):
        await send_admin_menu(update, edit=False)
    else:
        await update.effective_message.reply_text(
            f"⛔ شما دسترسی مدیریت ندارید.\n\n🆔 آیدی تلگرام شما: `{user.id}`\n\n"
            "لطفاً این آیدی را در متغیر ADMIN_IDS تنظیم کنید.",
            parse_mode="Markdown",
        )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.effective_message.reply_text("❌ عملیات جاری لغو شد.")
    return ConversationHandler.END


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text
    user = update.effective_user
    if user:
        try:
            database.add_user(user.id, user.username, user.full_name)
        except Exception as e:
            logger.error("Error adding user: %s", e)

    if text == "📦 محصولات و قیمت‌ها":
        await show_user_menu(update, context, parent_id=0)
    elif text == "📞 تماس با ما":
        contact_text = database.get_setting("contact_text", "تماس با ما")
        await update.message.reply_text(contact_text)
    elif text == "🔧 پنل مدیریت" and user and is_admin(user.id):
        await send_admin_menu(update, edit=False)


async def show_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, parent_id=0):
    chat_id = update.effective_chat.id
    buttons = database.get_buttons(parent_id, admin_mode=False)
    catalogs = database.get_catalogs(parent_id)

    if catalogs:
        for cat in catalogs:
            cap = cat.get("caption") or ""
            try:
                if cat["file_type"] == "photo":
                    await context.bot.send_photo(chat_id=chat_id, photo=cat["file_id"], caption=cap)
                else:
                    await context.bot.send_document(
                        chat_id=chat_id, document=cat["file_id"], caption=cap
                    )
            except Exception as e:
                logger.error("Error sending catalog %s: %s", cat.get("id"), e)
                await context.bot.send_message(chat_id=chat_id, text="⚠️ خطا در ارسال یکی از فایل‌ها.")

    keyboard = []
    for btn in buttons:
        title = (btn["title"] or "")[:64]
        keyboard.append([InlineKeyboardButton(title, callback_data=f"umenu_{btn['id']}")])

    if parent_id != 0:
        parent_btn = database.get_button(parent_id)
        back_id = parent_btn["parent_id"] if parent_btn else 0
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"umenu_{back_id}")])

    if keyboard:
        await context.bot.send_message(
            chat_id=chat_id,
            text="لطفاً گزینه مورد نظر را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    elif not catalogs:
        await context.bot.send_message(chat_id=chat_id, text="محتوایی در این بخش قرار ندارد.")


async def user_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        parent_id = int(query.data.split("_")[1])
    except (IndexError, ValueError):
        return
    try:
        await query.message.delete()
    except Exception:
        pass
    await show_user_menu(update, context, parent_id)


async def send_admin_menu(update: Update, edit: bool = False):
    user_count = database.get_user_count()
    keyboard = [
        [InlineKeyboardButton("📝 ویرایش متن خوش‌آمدگویی", callback_data="adm_welcome")],
        [InlineKeyboardButton("📞 ویرایش متن تماس با ما", callback_data="adm_contact")],
        [InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="adm_bc")],
        [InlineKeyboardButton("🗂️ مدیریت دکمه‌ها و فایل‌ها", callback_data="adm_tree_0")],
        [InlineKeyboardButton("📥 دانلود بک‌آپ دیتابیس (DB)", callback_data="adm_backup")],
        [InlineKeyboardButton("⚠️ ریست کامل سیستم", callback_data="adm_reset_prompt")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = (
        "🔧 **پنل مدیریت ربات توان سازه**\n\n"
        f"👥 تعداد کاربران ربات: `{user_count}` نفر"
    )
    if edit and update.callback_query and update.callback_query.message:
        try:
            await update.callback_query.edit_message_text(
                msg, reply_markup=reply_markup, parse_mode="Markdown"
            )
            return
        except BadRequest:
            pass
    await update.effective_message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")


async def render_admin_tree(message, parent_id: int, edit: bool = False):
    buttons = database.get_buttons(parent_id, admin_mode=True)
    catalogs = database.get_catalogs(parent_id)

    keyboard = []
    for b in buttons:
        title = (b["title"] or "")[:40]
        keyboard.append(
            [
                InlineKeyboardButton(f"📁 {title}", callback_data=f"adm_tree_{b['id']}"),
                InlineKeyboardButton("🗑️ حذف", callback_data=f"adm_delbtn_{b['id']}"),
            ]
        )

    for c in catalogs:
        label = (c.get("caption") or c.get("file_type") or "file")[:30]
        keyboard.append(
            [
                InlineKeyboardButton(f"📎 {label}", callback_data="adm_noop"),
                InlineKeyboardButton("🗑️ حذف فایل", callback_data=f"adm_delcat_{c['id']}"),
            ]
        )

    keyboard.append(
        [InlineKeyboardButton("➕ افزودن زیرمنو جدید", callback_data=f"adm_addbtn_{parent_id}")]
    )
    keyboard.append(
        [
            InlineKeyboardButton(
                "📤 آپلود کاتالوگ/عکس در این بخش", callback_data=f"adm_addcat_{parent_id}"
            )
        ]
    )

    if parent_id != 0:
        parent_btn = database.get_button(parent_id)
        back_id = parent_btn["parent_id"] if parent_btn else 0
        keyboard.append(
            [InlineKeyboardButton("🔙 بازگشت به بخش قبلی", callback_data=f"adm_tree_{back_id}")]
        )
    else:
        keyboard.append(
            [InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="adm_home")]
        )

    msg_text = (
        f"📂 **مدیریت بخش (شناسه: {parent_id})**\n"
        f"فایل‌های موجود در این بخش: {len(catalogs)} عدد"
    )
    markup = InlineKeyboardMarkup(keyboard)

    if edit:
        try:
            await message.edit_text(msg_text, reply_markup=markup, parse_mode="Markdown")
            return
        except BadRequest:
            pass
    await message.reply_text(msg_text, reply_markup=markup, parse_mode="Markdown")


async def admin_inline_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    if not user or not is_admin(user.id):
        await query.answer("دسترسی غیرمجاز!", show_alert=True)
        return

    data = query.data or ""
    await query.answer()

    if data == "adm_noop":
        return

    if data == "adm_home":
        await send_admin_menu(update, edit=True)
        return

    if data == "adm_backup":
        if os.path.exists(database.DB_PATH):
            try:
                with open(database.DB_PATH, "rb") as f:
                    await query.message.reply_document(
                        document=InputFile(f, filename="database_backup.db"),
                        caption="📥 فایل پشتیبان دیتابیس",
                    )
            except Exception as e:
                logger.error("Backup send error: %s", e)
                await query.message.reply_text("❌ خطا در ارسال فایل پشتیبان.")
        else:
            await query.message.reply_text("❌ فایل دیتابیس یافت نشد.")
        return

    if data == "adm_reset_prompt":
        keyboard = [
            [InlineKeyboardButton("✅ بله، ریست کامل شود", callback_data="confirm_sys_reset")],
            [InlineKeyboardButton("❌ انصراف", callback_data="cancel_sys_reset")],
        ]
        try:
            await query.edit_message_text(
                "⚠️ **هشدار بازنشانی کامل سیستم** ⚠️\n\n"
                "آیا اطمینان دارید؟ تمامی دکمه‌ها، کاتالوگ‌ها و تنظیمات متنی پاک شده "
                "و به حالت اولیه بازمی‌گردند.\n"
                "*(کاربران پاک نخواهند شد)*",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
            )
        except BadRequest:
            pass
        return

    if data == "confirm_sys_reset":
        if database.reset_bot_config():
            await query.edit_message_text("✅ تمامی دکمه‌ها، فایل‌ها و تنظیمات با موفقیت ریست شدند.")
        else:
            await query.edit_message_text("❌ خطا در بازنشانی اطلاعات.")
        return

    if data == "cancel_sys_reset":
        await query.edit_message_text("❌ عملیات ریست لغو شد.")
        return

    if data.startswith("adm_tree_"):
        try:
            parent_id = int(data.split("_")[2])
        except (IndexError, ValueError):
            return
        await render_admin_tree(query.message, parent_id, edit=True)
        return

    if data.startswith("adm_delbtn_"):
        try:
            btn_id = int(data.split("_")[2])
        except (IndexError, ValueError):
            return
        btn = database.get_button(btn_id)
        parent_id = btn["parent_id"] if btn else 0
        database.delete_button(btn_id)
        await render_admin_tree(query.message, parent_id, edit=True)
        return

    if data.startswith("adm_delcat_"):
        try:
            cat_id = int(data.split("_")[2])
        except (IndexError, ValueError):
            return
        cat = database.get_catalog(cat_id)
        parent_id = cat["button_id"] if cat else 0
        database.delete_catalog(cat_id)
        await render_admin_tree(query.message, parent_id, edit=True)
        return


async def admin_conv_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await admin_inline_callback(update, context)
    return ConversationHandler.END


async def prompt_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "لطفاً متن جدید خوش‌آمدگویی (/start) را بفرستید:\n(جهت لغو: /cancel)"
    )
    return STATE_EDIT_WELCOME


async def save_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await maybe_handle_main_menu(update, context):
        return ConversationHandler.END
    database.update_setting("welcome_text", update.message.text)
    await update.message.reply_text("✅ متن خوش‌آمدگویی ذخیره شد.")
    await send_admin_menu(update, edit=False)
    context.user_data.clear()
    return ConversationHandler.END


async def prompt_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "لطفاً متن جدید بخش تماس با ما را بفرستید:\n(جهت لغو: /cancel)"
    )
    return STATE_EDIT_CONTACT


async def save_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await maybe_handle_main_menu(update, context):
        return ConversationHandler.END
    database.update_setting("contact_text", update.message.text)
    await update.message.reply_text("✅ متن تماس با ما ذخیره شد.")
    await send_admin_menu(update, edit=False)
    context.user_data.clear()
    return ConversationHandler.END


async def prompt_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "لطفاً پیام عمومی خود (متن، عکس یا فایل) را بفرستید:\n(جهت لغو: /cancel)"
    )
    return STATE_BROADCAST


async def do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await maybe_handle_main_menu(update, context):
        return ConversationHandler.END

    users = database.get_all_users()
    msg = update.message
    count = 0
    failed = 0

    await update.message.reply_text(f"⏳ در حال ارسال به {len(users)} کاربر...")

    for u in users:
        try:
            await msg.copy(chat_id=u["user_id"])
            count += 1
        except Forbidden:
            failed += 1
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 0.5)
            try:
                await msg.copy(chat_id=u["user_id"])
                count += 1
            except Exception:
                failed += 1
        except TelegramError:
            failed += 1
        await asyncio.sleep(0.05)

    await update.message.reply_text(
        f"✅ پیام همگانی ارسال شد.\nموفق: {count}\nناموفق (مسدود): {failed}"
    )
    await send_admin_menu(update, edit=False)
    context.user_data.clear()
    return ConversationHandler.END


async def prompt_add_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        parent_id = int(query.data.split("_")[2])
    except (IndexError, ValueError):
        parent_id = 0
    context.user_data["target_parent_id"] = parent_id
    await query.message.reply_text("نام دکمه جدید را وارد کنید:\n(جهت لغو: /cancel)")
    return STATE_ADD_BTN


async def save_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await maybe_handle_main_menu(update, context):
        return ConversationHandler.END
    title = (update.message.text or "").strip()
    if not title:
        await update.message.reply_text("⚠️ نام دکمه نمی‌تواند خالی باشد. دوباره بفرستید یا /cancel")
        return STATE_ADD_BTN
    parent_id = context.user_data.get("target_parent_id", 0)
    database.add_menu_button(title, parent_id)
    await update.message.reply_text(f"✅ دکمه '{title}' اضافه شد.")
    await render_admin_tree(update.message, parent_id, edit=False)
    context.user_data.clear()
    return ConversationHandler.END


async def prompt_add_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        parent_id = int(query.data.split("_")[2])
    except (IndexError, ValueError):
        parent_id = 0
    context.user_data["target_cat_button_id"] = parent_id
    await query.message.reply_text(
        "لطفاً فایل کاتالوگ (PDF) یا عکس محصول را ارسال کنید:\n(جهت لغو: /cancel)"
    )
    return STATE_ADD_CATALOG_FILE


async def save_cat_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await maybe_handle_main_menu(update, context):
        return ConversationHandler.END

    msg = update.message
    if not msg:
        return STATE_ADD_CATALOG_FILE

    if msg.photo:
        file_id = msg.photo[-1].file_id
        file_type = "photo"
    elif msg.document:
        file_id = msg.document.file_id
        file_type = "document"
    else:
        await update.message.reply_text(
            "⚠️ لطفاً فقط تصویر یا فایل PDF ارسال کنید (ارسال /cancel برای لغو)."
        )
        return STATE_ADD_CATALOG_FILE

    context.user_data["cat_file_id"] = file_id
    context.user_data["cat_file_type"] = file_type
    await update.message.reply_text(
        "توضیحات یا درصد قیمت را وارد کنید (در صورت عدم نیاز '-' یا '0' بفرستید):"
    )
    return STATE_ADD_CATALOG_CAPTION


async def save_cat_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await maybe_handle_main_menu(update, context):
        return ConversationHandler.END

    caption = update.message.text or ""
    if caption in ["-", "0"]:
        caption = ""

    button_id = context.user_data.get("target_cat_button_id", 0)
    file_id = context.user_data.get("cat_file_id")
    file_type = context.user_data.get("cat_file_type")

    if not file_id:
        await update.message.reply_text("❌ فایل یافت نشد. از اول تلاش کنید.")
        context.user_data.clear()
        return ConversationHandler.END

    database.add_catalog(button_id, file_id, file_type, caption)
    await update.message.reply_text("✅ کاتالوگ/تصویر با موفقیت در این دکمه ذخیره شد.")
    await render_admin_tree(update.message, button_id, edit=False)
    context.user_data.clear()
    return ConversationHandler.END


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)


def create_bot_app():
    global ADMIN_IDS
    ADMIN_IDS = parse_admin_ids()
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("متغیر BOT_TOKEN در تنظیمات Railway تعریف نشده است!")

    logger.info("Loaded %s admin id(s): %s", len(ADMIN_IDS), ADMIN_IDS)

    app = (
        ApplicationBuilder()
        .token(token)
        .concurrent_updates(False)
        .build()
    )

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(prompt_welcome, pattern="^adm_welcome$"),
            CallbackQueryHandler(prompt_contact, pattern="^adm_contact$"),
            CallbackQueryHandler(prompt_broadcast, pattern="^adm_bc$"),
            CallbackQueryHandler(prompt_add_btn, pattern="^adm_addbtn_"),
            CallbackQueryHandler(prompt_add_cat, pattern="^adm_addcat_"),
        ],
        states={
            STATE_EDIT_WELCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_welcome)],
            STATE_EDIT_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_contact)],
            STATE_BROADCAST: [MessageHandler(filters.ALL & ~filters.COMMAND, do_broadcast)],
            STATE_ADD_BTN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_btn)],
            STATE_ADD_CATALOG_FILE: [
                MessageHandler(filters.ALL & ~filters.COMMAND, save_cat_file)
            ],
            STATE_ADD_CATALOG_CAPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_cat_caption)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            CommandHandler("admin", admin_command_handler),
            CallbackQueryHandler(
                admin_conv_fallback,
                pattern="^(adm_|confirm_sys_reset|cancel_sys_reset)",
            ),
        ],
        allow_reentry=True,
    )

    # conv_handler MUST be first so fallbacks can end an active conversation
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command_handler))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(user_menu_callback, pattern="^umenu_"))
    app.add_handler(
        CallbackQueryHandler(
            admin_inline_callback,
            pattern="^(adm_|confirm_sys_reset|cancel_sys_reset)",
        )
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)
    return app
