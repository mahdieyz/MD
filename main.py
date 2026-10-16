import os
import threading
import asyncio
import logging
from web_panel import app as flask_app
from bot import create_bot_app

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


def run_flask():
    """Run Flask web panel"""
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"🌐 Starting web panel on port {port}")
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)


def run_bot():
    """Run Telegram bot in a separate thread with its own event loop"""
    logger.info("🤖 Starting Telegram bot")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    bot_app = create_bot_app()

    try:
        loop.run_until_complete(bot_app.initialize())
        loop.run_until_complete(bot_app.start())
        loop.run_until_complete(bot_app.updater.start_polling(drop_pending_updates=True))
        logger.info("✅ Bot is running")
        loop.run_forever()
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        try:
            loop.run_until_complete(bot_app.updater.stop())
            loop.run_until_complete(bot_app.stop())
            loop.run_until_complete(bot_app.shutdown())
        except Exception:
            pass
        loop.close()


if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("🚀 Starting Tavansazeh Bot + Web Panel")
    logger.info("=" * 50)

    # Start bot in background thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Run Flask in main thread (Railway needs the web process on PORT)
    run_flask()
