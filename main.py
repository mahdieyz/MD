import os
import threading
import database
from web_panel import app as flask_app
from bot import create_bot_app

def run_flask():
    port = int(os.getenv("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    # ۱. ساخت دیتابیس و جداول
    database.init_db()
    
    # ۲. اجرای پنل وب روی Daemon Thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # ۳. اجرای ربات تلگرام روی Main Thread
    print("🚀 Starting Bot & Web Panel...")
    bot_app = create_bot_app()
    bot_app.run_polling(drop_pending_updates=True)
