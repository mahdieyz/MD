import os
import threading
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import database
from bot import create_bot_app

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()

    def log_message(self, format, *args):
        return


def run_health_server():
    try:
        port = int(os.getenv("PORT", 8080))
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        logger.info("Health check server listening on port %s", port)
        server.serve_forever()
    except Exception as e:
        logger.error("Health server error: %s", e)


if __name__ == "__main__":
    logger.info("Initializing database at %s ...", database.DB_PATH)
    database.init_db()

    logger.info("Starting health server thread...")
    threading.Thread(target=run_health_server, daemon=True).start()

    logger.info("Starting Telegram bot polling...")
    bot_app = create_bot_app()
    bot_app.run_polling(drop_pending_updates=True)
