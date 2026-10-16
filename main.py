import os
import threading
import logging
import time
from web_panel import app as flask_app

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"🌐 Starting Web Admin Panel on port {port}")
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def run_bot():
    token = os.environ.get('BOT_TOKEN', '').strip()
    if not token:
        logger.error("❌ BOT_TOKEN environment variable is missing!")
        return

    try:
        from bot import create_bot_app
        logger.info("🤖 Starting Telegram Bot...")
        bot_app = create_bot_app()
        bot_app.run_polling(drop_pending_updates=True)
    except Exception as e:
        logger.error(f"❌ Telegram Bot error: {e}", exc_info=True)

if __name__ == '__main__':
    logger.info("🚀 Launching Tavansazeh System")
    
    # Run Web Admin Panel in daemon background thread
    web_thread = threading.Thread(target=run_flask, daemon=True)
    web_thread.start()
    
    # Run Telegram Bot polling in main thread
    run_bot()
