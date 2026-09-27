"""Open the job list with a working "Pull latest jobs" button.

    python app.py              opens http://127.0.0.1:8765 in your browser
    python app.py --port 9000

The button runs commands/refresh.py (pull → Notion → rebuild the page) and shows
its progress live. The "Add job" box does the same with a pasted link instead of a pull. Leave this window open while you use the page; Ctrl+C stops it.
Only this computer can reach it (it listens on 127.0.0.1).
"""

import argparse
import json
import sys
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from commands import refresh
from commands.dashboard import main as build_dashboard
from jobmax.config import ROOT

PAGE = ROOT / "out" / "dashboard.html"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class Progress:
    """One refresh at a time, and what it has said so far. Shared by the request threads."""

    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.lines: list[str] = []
        self.step = (0, 0, "")
        self.part: tuple[float, str] | None = None  # how far through the current step, if it says
        self.started = 0.0
        self.failed: list[str] | None = None

    def start(self, **options) -> bool:
        """Start refresh.run(**options) in the background, unless one is already running."""
        with self.lock:
            if self.running:
                return False
            self.running, self.lines, self.step, self.failed = True, [], (0, 0, "Starting"), None
            self.part, self.started = None, time.monotonic()
        threading.Thread(target=self._run, kwargs=options, daemon=True).start()
        return True

    def _run(self, **options):
        failed = ["refresh"]
        try:
            failed = refresh.run(self._say, on_step=self._on_step, on_progress=self._on_progress, **options)
        except Exception as err:  # never leave the button stuck on "running"
            self._say(f"Stopped: {err}")
        finally:
            with self.lock:
                self.running, self.failed = False, failed

    def _say(self, line: str):
        print(line)
        with self.lock:
            self.lines.append(line)

    def _on_step(self, i: int, n: int, name: str):
        with self.lock:
            self.step, self.part = (i, n, name), None

    def _on_progress(self, part: float, text: str):
        with self.lock:
            self.part = (part, text)

    def snapshot(self, since: int) -> dict:
        with self.lock:
            i, n, name = self.step
            part, detail = self.part or (None, "")
            return {"running": self.running, "step": i, "steps": n, "name": name,
                    "part": part, "detail": detail,
                    "elapsed": round(time.monotonic() - self.started) if self.started else 0,
                    "lines": self.lines[since:], "next": len(self.lines), "failed": self.failed}


PROGRESS = Progress()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/":
            self._send(HTTPStatus.OK, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/progress":
            since = parse_qs(url.query).get("since", ["0"])[0]
            self._json(PROGRESS.snapshot(int(since) if since.isdigit() else 0))
        else:
            self._send(HTTPStatus.NOT_FOUND, b"Not found", "text/plain")

    def do_POST(self):
        # Pulls cost money. A custom header can't be sent by another website without a
        # CORS preflight, which this server never approves, so only the page itself can start one.
        if self.path not in ("/pull", "/add") or self.headers.get("X-Jobmax") != "1":
            self._send(HTTPStatus.FORBIDDEN, b"Forbidden", "text/plain")
            return
        if self.path == "/pull":
            started = PROGRESS.start()
        else:
            try:
                length = int(self.headers.get("Content-Length") or 0)
                link = json.loads(self.rfile.read(min(length, 10_000)) or b"{}").get("url", "")
            except (ValueError, AttributeError):
                link = ""
            if not (isinstance(link, str) and link.strip().startswith(("http://", "https://"))):
                self._json({"error": "Paste a full link, starting with https://"}, HTTPStatus.BAD_REQUEST)
                return
            started = PROGRESS.start(links=[link.strip()])
        self._json({"started": started}, HTTPStatus.ACCEPTED if started else HTTPStatus.CONFLICT)

    def _json(self, data: dict, status=HTTPStatus.OK):
        self._send(status, json.dumps(data).encode(), "application/json")

    def _send(self, status, body: bytes, kind: str):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # the progress lines are enough; skip per-request noise
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if not PAGE.exists() and build_dashboard([]) != 0:
        return 1
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Job list at {url}  (Ctrl+C to stop)")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
