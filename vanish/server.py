"""Локальный HTTP-сервер: API + собранный интерфейс. Слушает только 127.0.0.1."""

from __future__ import annotations

import json
import mimetypes
import os
import sqlite3
import threading
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import STATIC_DIR, api
from .store import connect

HOST = "127.0.0.1"
MAX_BODY = 20 * 1024 * 1024
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")


class LocalServer(ThreadingHTTPServer):
    # На Windows SO_REUSEADDR позволяет «угнать» уже занятый порт — отключаем.
    allow_reuse_address = os.name != "nt"


class App:
    def __init__(self, db_path: Path, static_dir: Path = STATIC_DIR):
        self.conn: sqlite3.Connection = connect(db_path)
        self.lock = threading.Lock()
        self.static_dir = static_dir


def make_handler(app: App, port_holder: dict):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Vanish"
        sys_version = ""

        def log_message(self, fmt, *args):  # тихий режим: никаких логов с данными
            pass

        # --- защита -----------------------------------------------------------
        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").lower()
            port = port_holder["port"]
            return host in {f"127.0.0.1:{port}", f"localhost:{port}"}

        def _origin_ok(self) -> bool:
            origin = self.headers.get("Origin")
            if not origin:
                return True
            port = port_holder["port"]
            return origin in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

        # --- ответы -----------------------------------------------------------
        def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                "connect-src 'self'; font-src 'self' data:; worker-src 'self' blob:; frame-ancestors 'none'",
            )
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, data, status: int = 200):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8", {"Cache-Control": "no-store"})

        def _error(self, status: int, message: str):
            self._json({"error": message}, status)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise api.ApiError("Слишком большой запрос")
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(data, dict):
                raise api.ApiError("Ожидался JSON-объект")
            return data

        # --- маршруты ---------------------------------------------------------
        def do_GET(self):
            if not self._host_ok():
                return self._error(HTTPStatus.FORBIDDEN, "Forbidden host")
            path = urlparse(self.path).path
            try:
                if path == "/api/state":
                    with app.lock:
                        return self._json(api.full_state(app.conn))
                if path == "/api/export.csv":
                    with app.lock:
                        body = api.export_csv(app.conn).encode("utf-8")
                    name = f"vanish-report-{datetime.now():%Y-%m-%d}.csv"
                    return self._send(200, body, "text/csv; charset=utf-8",
                                      {"Content-Disposition": f'attachment; filename="{name}"',
                                       "Cache-Control": "no-store"})
                if path == "/api/progress.json":
                    with app.lock:
                        data = api.export_progress(app.conn)
                    body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
                    name = f"vanish-progress-{datetime.now():%Y-%m-%d}.json"
                    return self._send(200, body, "application/json; charset=utf-8",
                                      {"Content-Disposition": f'attachment; filename="{name}"',
                                       "Cache-Control": "no-store"})
                if path.startswith("/api/"):
                    return self._error(HTTPStatus.NOT_FOUND, "Not found")
                return self._static(path)
            except api.ApiError as e:
                return self._error(HTTPStatus.BAD_REQUEST, str(e))

        do_HEAD = do_GET

        def do_POST(self):
            if not self._host_ok() or not self._origin_ok():
                return self._error(HTTPStatus.FORBIDDEN, "Forbidden origin")
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Нужен application/json")
            path = urlparse(self.path).path
            try:
                data = self._body()
                with app.lock:
                    if path == "/api/decide":
                        return self._json(api.decide(app.conn, str(data.get("domain", "")), data.get("decision")))
                    if path == "/api/update":
                        return self._json(api.update(app.conn, str(data.get("domain", "")), data.get("fields") or {}))
                    if path == "/api/bulk":
                        return self._json(api.bulk(app.conn, str(data.get("action", ""))))
                    if path == "/api/undo":
                        return self._json(api.undo(app.conn))
                    if path == "/api/services":
                        return self._json(api.add_service(
                            app.conn, str(data.get("domain", "")), str(data.get("name") or ""),
                            data.get("decision"),
                        ))
                    if path == "/api/progress/import":
                        return self._json(api.import_progress(app.conn, data.get("data")))
                return self._error(HTTPStatus.NOT_FOUND, "Not found")
            except api.ApiError as e:
                app.conn.rollback()
                return self._error(HTTPStatus.BAD_REQUEST, str(e))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return self._error(HTTPStatus.BAD_REQUEST, "Некорректный JSON")

        def _static(self, path: str):
            root = app.static_dir.resolve()
            if not (root / "index.html").exists():
                msg = ("Интерфейс не собран. Выполните: python -m vanish build").encode("utf-8")
                return self._send(500, msg, "text/plain; charset=utf-8")
            rel = path.lstrip("/") or "index.html"
            target = (root / rel).resolve()
            if root not in target.parents and target != root or not target.is_file():
                target = root / "index.html"  # SPA-фолбэк
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype == "application/javascript":
                ctype += "; charset=utf-8"
            cache = "no-cache" if target.name == "index.html" else "public, max-age=31536000, immutable"
            self._send(200, target.read_bytes(), ctype, {"Cache-Control": cache})

    return Handler


def serve(db_path: Path, port: int = 8765, open_browser: bool = True) -> None:
    app = App(db_path)
    port_holder = {"port": port}
    httpd = None
    for candidate in range(port, port + 20):
        try:
            port_holder["port"] = candidate
            httpd = LocalServer((HOST, candidate), make_handler(app, port_holder))
            break
        except OSError:
            continue
    if httpd is None:
        raise SystemExit(f"Не удалось занять порт {port}–{port + 19}")
    url = f"http://127.0.0.1:{port_holder['port']}/"
    print(f"\n  Vanish запущен: {url}")
    print("  Остановить: Ctrl+C\n", flush=True)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Пока! Прогресс сохранён.")
    finally:
        httpd.server_close()
        app.conn.close()
