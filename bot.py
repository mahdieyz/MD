import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler
)
import database

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip() and x.strip().isdigit()]

(STATE_EDIT_WELCOME, STATE_EDIT_CONTACT, STATE_BROADCAST, 
 STATE_ADD_BTN, STATE_ADD_CATALOG_FILE, STATE_ADD_CATALOG_CAPTION) = range(6)

def is_admin(user_id):
    return user_id in ADMIN_IDS if user_id else False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user = update.effective_user
    if user:
        database.add_user(user.id, user.username, user.full_name)
    
    welcome_text = database.get_setting("welcome_text", "به ربات توان سازه خوش آمدید.")
    
    keyboard = [[KeyboardButton("📦 محصولات و قیمت‌ها")], [KeyboardButton("📞 تماس با ما")]]
    if user and is_admin(user.id):
        keyboard.append([KeyboardButton("🔧 پنل مدیریت")])
        
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.effective_message.reply_text(welcome_text, reply_markup=reply_markup)

async def admin_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user = update.effective_user
    if user and is_admin(user.id):
        await send_admin_menu(update)
    else:
        await update.effective_message.reply_text("⛔ شما دسترسی مدیریت ندارید.")

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
        database.add_user(user.id, user.username, user.full_name)
    
    if text == "📦 محصولات و قیمت‌ها":
        await show_user_menu(update, context, parent_id=0)
    elif text == "📞 تماس با ما":
        contact_text = database.get_setting("contact_text", "تماس با ما")
        await update.message.reply_text(contact_text)
    elif text == "🔧 پنل مدیریت" and user and is_admin(user.id):
        await send_admin_menu(update)

async def show_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, parent_id=0):
    chat_id = update.effective_chat.id
    buttons = database.get_buttons(parent_id, admin_mode=False)
    catalogs = database.get_catalogs(parent_id)
    
    if catalogs:
        for cat in catalogs:
            cap = cat.get('caption') or ""
            if cat['file_type'] == 'photo':
                await context.bot.send_photo(chat_id=chat_id, photo=cat['file_id'], caption=cap)
            else:
                await context.bot.send_document(chat_id=chat_id, document=cat['file_id'], caption=cap)
                
    keyboard = []
    for btn in buttons:
        keyboard.append([InlineKeyboardButton(btn['title'], callback_data=f"umenu_{btn['id']}")])
        
    if parent_id != 0:
        parent_btn = database.get_button(parent_id)
        back_id = parent_btn['parent_id'] if parent_btn else 0
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"umenu_{back_id}")])
        
    if keyboard:
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(chat_id=chat_id, text="لطفاً گزینه مورد نظر را انتخاب کنید:", reply_markup=reply_markup)
    elif not catalogs:
        await context.bot.send_message(chat_id=chat_id, text="محتوایی در این بخش قرار ندارد.")

async def user_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parent_id = int(query.data.split("_")[1])
    try:
        await query.message.delete()
    except Exception:
        pass
    await show_user_menu(update, context, parent_id)

# --- مدیریت ربات ---

async def send_admin_menu(update: Update):
    target_msg = update.effective_message
    user_count = database.get_user_count()
    
    keyboard = [
        [InlineKeyboardButton("📝 ویرایش متن خوش‌آمدگویی", callback_data="adm_welcome")],
        [InlineKeyboardButton("📞 ویرایش متن تماس با ما", callback_data="adm_contact")],
        [InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="adm_bc")],
        [InlineKeyboardButton("🗂️ مدیریت دکمه‌ها و فایل‌ها", callback_data="adm_tree_0")],
        [InlineKeyboardButton("📥 دانلود بک‌آپ دیتابیس (DB)", callback_data="adm_backup")],
        [InlineKeyboardButton("⚠️ ریست کامل سیستم", callback_data="adm_reset_prompt")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = f"🔧 **پنل مدیریت ربات توان سازه**\n\n👥 تعداد کاربران ربات: `{user_count}` نفر"
    await target_msg.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")

async def admin_inline_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await query.answer("دسترسی غیرمجاز!", show_alert=True)
        return

    data = query.data
    await query.answer()

    if data == "adm_backup":
        if os.path.exists(database.DB_PATH):
            await query.message.reply_document(document=open(database.DB_PATH, "rb"), filename="database_backup.db", caption="📥 فایل پشتیبان دیتابیس")
        else:
            await query.message.reply_text("❌ فایل دیتابیس یافت نشد.")

    elif data == "adm_reset_prompt":
        keyboard = [
            [InlineKeyboardButton("✅ بله، ریست کامل شود", callback_data="confirm_sys_reset")],
            [InlineKeyboardButton("❌ انصراف", callback_data="cancel_sys_reset")]
        ]
        await query.edit_message_text(
            "⚠️ **هشدار بازنشانی کامل سیستم** ⚠️\n\n"
            "آیا اطمینان دارید؟ تمامی دکمه‌ها، کاتالوگ‌ها و تنظیمات متنی پاک شده و به حالت اولیه بازمی‌گردند.\n"
            "*(کاربران پاک نخواهند شد)*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    elif data == "confirm_sys_reset":
        if database.reset_bot_config():
            await query.edit_message_text("✅ تمامی دکمه‌ها، فایل‌ها و تنظیمات با موفقیت ریست شدند.")
        else:
            await query.edit_message_text("❌ خطا در بازنشانی اطلاعات.")
    elif data == "cancel_sys_reset":
        await query.edit_message_text("❌ عملیات ریست لغو شد.")

    elif data.startswith("adm_tree_"):
        parent_id = int(data.split("_")[2])
        buttons = database.get_buttons(parent_id, admin_mode=True)
        catalogs = database.get_catalogs(parent_id)
        
        keyboard = []
        for b in buttons:
            keyboard.append([
                InlineKeyboardButton(f"📁 {b['title']}", callback_data=f"adm_tree_{b['id']}"),
                InlineKeyboardButton("🗑️ حذف", callback_data=f"adm_delbtn_{b['id']}")
            ])
            
        keyboard.append([InlineKeyboardButton("➕ افزودن زیرمنو جدید", callback_data=f"adm_addbtn_{parent_id}")])
        keyboard.append([InlineKeyboardButton("📤 آپلود کاتالوگ/عکس در این بخش", callback_data=f"adm_addcat_{parent_id}")])
        
        if parent_id != 0:
            parent_btn = database.get_button(parent_id)
            back_id = parent_btn['parent_id'] if parent_btn else 0
            keyboard.append([InlineKeyboardButton("🔙 بازگشت به بخش قبلی", callback_data=f"adm_tree_{back_id}")])

        msg_text = f"📂 **مدیریت بخش (شناسه: {parent_id})**\nفایل‌های موجود در این بخش: {len(catalogs)} عدد"
        await query.edit_message_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("adm_delbtn_"):
        btn_id = int(data.split("_")[2])
        database.delete_button(btn_id)
        await query.edit_message_text("✅ دکمه و فایل‌های وابسته با موفقیت حذف شدند.")

# --- گفتگوهای مدیریت ---

async def prompt_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("لطفاً متن جدید خوش‌آمدگویی (/start) را بفرستید:\n(جهت لغو: /cancel)")
    return STATE_EDIT_WELCOME

async def save_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    database.update_setting("welcome_text", update.message.text)
    await update.message.reply_text("✅ متن خوش‌آمدگویی ذخیره شد.")
    return ConversationHandler.END

async def prompt_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("لطفاً متن جدید بخش تماس با ما را بفرستید:\n(جهت لغو: /cancel)")
    return STATE_EDIT_CONTACT

async def save_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    database.update_setting("contact_text", update.message.text)
    await update.message.reply_text("✅ متن تماس با ما ذخیره شد.")
    return ConversationHandler.END

async def prompt_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("لطفاً پیام عمومی خود (متن، عکس یا فایل) را بفرستید:\n(جهت لغو: /cancel)")
    return STATE_BROADCAST

async def do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = database.get_all_users()
    msg = update.message
    count = 0
    failed = 0
    for u in users:
        try:
            await msg.copy(chat_id=u['user_id'])
            count += 1
        except Exception:
            failed += 1
    await update.message.reply_text(f"✅ پیام همگانی ارسال شد.\nموفق: {count}\nناموفق (مسدود): {failed}")
    return ConversationHandler.END

async def prompt_add_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parent_id = int(query.data.split("_")[2])
    context.user_data['target_parent_id'] = parent_id
    await query.message.reply_text("نام دکمه جدید را وارد کنید:\n(جهت لغو: /cancel)")
    return STATE_ADD_BTN

async def save_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text
    parent_id = context.user_data.get('target_parent_id', 0)
    database.add_menu_button(title, parent_id)
    await update.message.reply_text(f"✅ دکمه '{title}' اضافه شد.")
    return ConversationHandler.END

async def prompt_add_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parent_id = int(query.data.split("_")[2])
    context.user_data['target_cat_button_id'] = parent_id
    await query.message.reply_text("لطفاً فایل کاتالوگ (PDF) یا عکس محصول را ارسال کنید:\n(جهت لغو: /cancel)")
    return STATE_ADD_CATALOG_FILE

async def save_cat_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await update.message.reply_text("⚠️ لطفاً فقط تصویر یا فایل PDF ارسال کنید (ارسال /cancel برای لغو).")
        return STATE_ADD_CATALOG_FILE

    context.user_data['cat_file_id'] = file_id
    context.user_data['cat_file_type'] = file_type
    await update.message.reply_text("توضیحات یا درصد قیمت را وارد کنید (در صورت عدم نیاز '-' یا '0' بفرستید):")
    return STATE_ADD_CATALOG_CAPTION

async def save_cat_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = update.message.text
    if caption in ["-", "0"]:
        caption = ""
    
    button_id = context.user_data.get('target_cat_button_id', 0)
    file_id = context.user_data.get('cat_file_id')
    file_type = context.user_data.get('cat_file_type')
    
    database.add_catalog(button_id, file_id, file_type, caption)
    await update.message.reply_text("✅ کاتالوگ/تصویر با موفقیت در این دکمه ذخیره شد.")
    return ConversationHandler.END

def create_bot_app():
    if not BOT_TOKEN:
        raise ValueError("متغیر BOT_TOKEN در تنظیمات Railway تعریف نشده است!")
        
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
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
                MessageHandler(filters.PHOTO | filters.Document.ALL, save_cat_file),
                MessageHandler(filters.ALL & ~filters.COMMAND, save_cat_file)
            ],
            STATE_ADD_CATALOG_CAPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_cat_caption)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            CommandHandler("admin", admin_command_handler)
        ],
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command_handler))
    app.add_handler(CommandHandler("cancel", cancel))
    
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(user_menu_callback, pattern="^umenu_"))
    app.add_handler(CallbackQueryHandler(admin_inline_callback, pattern="^(adm_|confirm_sys_reset|cancel_sys_reset)"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    return app
