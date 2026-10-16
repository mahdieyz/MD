import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import database
from bot import create_bot_app

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        return

def run_health_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    server.serve_forever()

if __name__ == "__main__":
    database.init_db()
    
    # سرور سبک جهت پاسخ به پورت Railway
    threading.Thread(target=run_health_server, daemon=True).start()
    
    print("🚀 Bot is launching...")
    bot_app = create_bot_app()
    bot_app.run_polling(drop_pending_updates=True)
