import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler
)
import database

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# Conversation states mapped within safe range
(WAITING_WELCOME, WAITING_CONTACT, WAITING_BROADCAST, 
 WAITING_NEW_BUTTON, WAITING_CATALOG_FILE, WAITING_CATALOG_TEXT) = range(6)

def is_admin(user_id):
    return user_id in ADMIN_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    database.add_user(user.id, user.username, user.full_name)
    
    welcome_text = database.get_setting("welcome_text", "خوش آمدید!")
    
    keyboard = [[KeyboardButton("📦 محصولات")], [KeyboardButton("📞 تماس با ما")]]
    if is_admin(user.id):
        keyboard.append([KeyboardButton("🔧 پنل مدیریت")])
        
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "📦 محصولات":
        await show_menu(update, context, parent_id=0)
    elif text == "📞 تماس با ما":
        contact_text = database.get_setting("contact_text", "پشتیبانی")
        await update.message.reply_text(contact_text)
    elif text == "🔧 پنل مدیریت" and is_admin(user_id):
        await send_admin_panel(update)

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, parent_id=0):
    buttons = database.get_buttons(parent_id, admin_mode=False)
    catalogs = database.get_catalogs(parent_id)
    
    if catalogs:
        for cat in catalogs:
            caption = cat.get('caption') or ""
            if cat['file_type'] == 'photo':
                await update.effective_message.reply_photo(cat['file_id'], caption=caption)
            else:
                await update.effective_message.reply_document(cat['file_id'], caption=caption)
                
    if buttons:
        keyboard = []
        for btn in buttons:
            keyboard.append([InlineKeyboardButton(btn['title'], callback_data=f"menu_{btn['id']}")])
        
        btn_data = database.get_button(parent_id)
        if btn_data and btn_data['parent_id'] != 0:
            keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"menu_{btn_data['parent_id']}")])
        elif parent_id != 0:
            keyboard.append([InlineKeyboardButton("🔙 بازگشت به اصلی", callback_data="menu_0")])
            
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.effective_message.reply_text("لطفاً یک گزینه را انتخاب کنید:", reply_markup=reply_markup)

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data.startswith("menu_"):
        parent_id = int(data.split("_")[1])
        await query.message.delete()
        await show_menu(update, context, parent_id)

# --- Admin Section & Reset ---

async def send_admin_panel(update: Update):
    keyboard = [
        [InlineKeyboardButton("📝 ویرایش متن خوش‌آمدگویی", callback_data="admin_edit_welcome")],
        [InlineKeyboardButton("📞 ویرایش تماس با ما", callback_data="admin_edit_contact")],
        [InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="admin_broadcast")],
        [InlineKeyboardButton("➕ افزودن دکمه ریشه", callback_data="admin_add_root_btn")],
        [InlineKeyboardButton("⚠️ ریست کامل سیستم", callback_data="admin_reset_sys")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🔧 به پنل مدیریت خوش آمدید:", reply_markup=reply_markup)

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.answer("شما ادمین نیستید!", show_alert=True)
        return
        
    data = query.data
    
    if data == "admin_reset_sys":
        keyboard = [
            [InlineKeyboardButton("✅ بله، ریست کامل شود", callback_data="confirm_sys_reset")],
            [InlineKeyboardButton("❌ انصراف", callback_data="cancel_sys_reset")]
        ]
        await query.edit_message_text(
            "⚠️ **هشدار بازنشانی سیستم** ⚠️\n\n"
            "آیا اطمینان دارید؟ این عملیات دکمه‌ها، کاتالوگ‌ها و تنظیمات را حذف کرده و به حالت اولیه برمی‌گرداند!\n"
            "*(کاربران حفظ می‌شوند)*", 
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
    elif data == "confirm_sys_reset":
        if database.reset_bot_config():
            await query.edit_message_text("✅ سیستم با موفقیت به تنظیمات کارخانه بازگشت.")
        else:
            await query.edit_message_text("❌ خطا در ریست سیستم.")
            
    elif data == "cancel_sys_reset":
        await query.edit_message_text("❌ عملیات ریست لغو شد.")
    
    await query.answer()

# Setup Application
def setup_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    
    # Admin Handlers
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^(admin_reset_sys|confirm_sys_reset|cancel_sys_reset)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    return app
