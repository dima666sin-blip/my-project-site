from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from pathlib import Path
import os
import json
import html as html_lib
from datetime import datetime

# Production configuration comes from Render environment variables.
# For local use, create config.py from config.py.example.
try:
    from config import BOT_TOKEN as LOCAL_BOT_TOKEN, CHAT_ID as LOCAL_CHAT_ID
except ImportError:
    LOCAL_BOT_TOKEN = ""
    LOCAL_CHAT_ID = ""

BOT_TOKEN = os.environ.get("BOT_TOKEN", LOCAL_BOT_TOKEN)
CHAT_ID = os.environ.get("CHAT_ID", LOCAL_CHAT_ID or "8976917219")

BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "index.html"
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8765"))

PRODUCTS = {
    "Теория для индивидуального проекта": 499,
    "Изготовление презентаций": 199,
    "Изготовление учебных пособий": 299,
}


def send_telegram(order):
    esc = html_lib.escape
    message = (
        "🛒 <b>Новый заказ!</b>\n\n"
        f"📦 <b>Товар:</b> {esc(order['product'])}\n"
        f"💰 <b>Цена:</b> {order['price']} ₽\n"
        f"👤 <b>ФИО:</b> {esc(order['fullName'])}\n"
        f"📝 <b>Описание:</b> {esc(order['orderDesc'])}\n"
        f"📧 <b>Почта:</b> {esc(order['email'])}\n"
        f"⏰ <b>Время:</b> {datetime.now().astimezone().strftime('%d.%m.%Y %H:%M:%S %z')}"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }, ensure_ascii=False).encode("utf-8")

    req = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
            data = json.loads(body)
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram HTTP {e.code}: {body}")
    except URLError as e:
        raise RuntimeError(f"Не удалось подключиться к Telegram: {e.reason}")
    except json.JSONDecodeError:
        raise RuntimeError("Telegram вернул некорректный ответ")

    if not data.get("ok"):
        raise RuntimeError(data.get("description", "Telegram вернул ошибку"))


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_html(self, raw):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            try:
                self._send_html(INDEX_FILE.read_bytes())
            except OSError as e:
                self._send_json(500, {"ok": False, "error": f"Не удалось открыть index.html: {e}"})
            return

        if path == "/health":
            self._send_json(200, {"ok": True, "server": "telegram-order", "port": PORT})
            return

        self._send_json(404, {"ok": False, "error": "Страница не найдена", "path": path})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != "/api/order":
            self._send_json(404, {"ok": False, "error": "Метод не найден", "path": path})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 100_000:
                raise ValueError("Некорректный размер запроса")

            raw = self.rfile.read(length).decode("utf-8", errors="strict")
            data = json.loads(raw)
            product = str(data.get("product", "")).strip()
            full_name = str(data.get("fullName", "")).strip()
            order_desc = str(data.get("orderDesc", "")).strip()
            email = str(data.get("email", "")).strip()

            if product not in PRODUCTS:
                raise ValueError("Неизвестный товар")
            if not full_name or not order_desc or not email:
                raise ValueError("Заполните все поля")

            order = {
                "product": product,
                "price": PRODUCTS[product],
                "fullName": full_name,
                "orderDesc": order_desc,
                "email": email,
            }

            send_telegram(order)
            self._send_json(200, {"ok": True, "message": "Заказ отправлен в Telegram"})

        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "Сервер получил некорректный JSON"})
        except Exception as e:
            print(f"Ошибка заказа: {e}")
            self._send_json(500, {"ok": False, "error": str(e)})

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")


if __name__ == "__main__":
    if not BOT_TOKEN or BOT_TOKEN.startswith("ВСТАВЬТЕ_СЮДА"):
        raise SystemExit("Сначала откройте config.py и вставьте токен бота из BotFather.")

    print(f"Сайт запущен на {HOST}:{PORT}")
    print(f"Порт: {PORT}")
    print("Для остановки нажмите Ctrl+C")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
