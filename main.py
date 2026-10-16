import os
import sys
import time
import logging
import threading
import asyncio

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger("main")

BOT_READY = False
BOT_ERROR = None


def run_flask():
    from web_panel import app as flask_app
    port = int(os.environ.get("PORT", 8080))
    logger.info("Starting web panel on 0.0.0.0:%s", port)
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


def run_bot():
    global BOT_READY, BOT_ERROR

    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        BOT_ERROR = "BOT_TOKEN is missing"
        logger.error("BOT_TOKEN is missing")
        return

    try:
        from bot import create_bot_app

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        app = create_bot_app()

        async def _start():
            global BOT_READY
            await app.initialize()
            await app.start()
            await app.updater.start_polling(drop_pending_updates=True)
            BOT_READY = True
            logger.info("Telegram bot is polling")
            # Keep the loop alive forever
            while True:
                await asyncio.sleep(3600)

        loop.run_until_complete(_start())
    except Exception as e:
        BOT_ERROR = str(e)
        logger.exception("Telegram bot crashed: %s", e)


if __name__ == "__main__":
    logger.info("=== Tavansazeh boot ===")
    logger.info("BOT_TOKEN set: %s", bool(os.environ.get("BOT_TOKEN")))
    logger.info("ADMIN_IDS set: %s", bool(os.environ.get("ADMIN_IDS")))
    logger.info("DB_PATH: %s", os.environ.get("DB_PATH", "bot_database.db"))

    bot_thread = threading.Thread(target=run_bot, name="telegram-bot", daemon=True)
    bot_thread.start()

    # Give bot a moment to connect; web must still bind quickly for Railway
    time.sleep(2)
    if BOT_ERROR:
        logger.error("Bot failed at startup: %s", BOT_ERROR)
    elif BOT_READY:
        logger.info("Bot reported ready")
    else:
        logger.warning("Bot still starting...")

    run_flask()
