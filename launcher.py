from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


def _resource_path(relative_path: str) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")) / relative_path
    return Path(__file__).resolve().parent / relative_path


def _open_browser_when_ready(url: str, timeout_seconds: float = 30.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            import urllib.request

            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except Exception:
            time.sleep(0.5)


class _BrowserHeartbeatMonitor:
    def __init__(self, idle_timeout_seconds: float = 25.0, check_interval_seconds: float = 5.0) -> None:
        self.idle_timeout_seconds = idle_timeout_seconds
        self.check_interval_seconds = check_interval_seconds
        self._last_seen: float | None = None
        self._lock = threading.Lock()

    def beat(self) -> None:
        with self._lock:
            self._last_seen = time.time()

    def should_shutdown(self) -> bool:
        with self._lock:
            if self._last_seen is None:
                return False
            return (time.time() - self._last_seen) > self.idle_timeout_seconds


def _start_browser_watchdog() -> tuple[_BrowserHeartbeatMonitor, ThreadingHTTPServer]:
    monitor = _BrowserHeartbeatMonitor()

    class HeartbeatHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/heartbeat":
                monitor.beat()
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                return

            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), HeartbeatHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return monitor, server


def _watch_browser_and_exit(monitor: _BrowserHeartbeatMonitor) -> None:
    while True:
        time.sleep(monitor.check_interval_seconds)
        if monitor.should_shutdown():
            os._exit(0)


def main() -> None:
    app_path = _resource_path("app.py")
    if not app_path.exists():
        raise FileNotFoundError(f"找不到应用入口文件: {app_path}")

    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.environ["STREAMLIT_SERVER_WEBSOCKET_PING_INTERVAL"] = "20"
    os.environ["STREAMLIT_SERVER_MAX_MESSAGE_SIZE"] = "2097152"

    monitor, watchdog_server = _start_browser_watchdog()
    os.environ["TEACHINGAI_BROWSER_WATCHDOG_URL"] = (
        f"http://127.0.0.1:{watchdog_server.server_address[1]}/heartbeat"
    )

    from streamlit.web.cli import main as streamlit_main

    threading.Thread(
        target=_open_browser_when_ready,
        args=("http://localhost:8501/",),
        daemon=True,
    ).start()
    threading.Thread(target=_watch_browser_and_exit, args=(monitor,), daemon=True).start()

    streamlit_main(
        args=[
            "run",
            str(app_path),
            "--global.developmentMode=false",
            "--server.address=localhost",
            "--server.port=8501",
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
            "--browser.serverAddress=localhost",
            "--browser.serverPort=8501",
            "--server.fileWatcherType=none",
        ],
        prog_name="streamlit",
        standalone_mode=False,
    )


if __name__ == "__main__":
    main()
