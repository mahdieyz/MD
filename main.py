import os
import threading
import logging
import time
from web_panel import app as flask_app
from bot import create_bot_app

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


def run_flask():
    """Run Flask Web Admin Panel in a daemon thread"""
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"🌐 Starting Web Admin Panel on 0.0.0.0:{port}")
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)


def run_bot():
    """Run Telegram bot in the main thread with PTB polling"""
    logger.info("🤖 Initializing Telegram Bot...")
    bot_app = create_bot_app()
    logger.info("✅ Telegram Bot initialized successfully. Starting polling...")
    bot_app.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🚀 Starting Tavansazeh Telegram Bot + Web Control Panel")
    logger.info("=" * 60)

    # Start Flask Web Panel in background thread
    web_thread = threading.Thread(target=run_flask, daemon=True)
    web_thread.start()

    time.sleep(1)

    # Run Telegram bot in main thread
    run_bot()
