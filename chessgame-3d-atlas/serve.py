#!/usr/bin/env python3
"""Static server for the ChessGame 3D Atlas export.

`python3 -m http.server` is fine for a quick look, but it is a single-threaded
copy loop with per-request stat calls and noisy ConnectionResetError tracebacks
whenever a browser cancels a large download (the atlas is one 4.6 MB HTML file,
so reloads and preview proxies do this a lot).

This server keeps the same simplicity but:
  * serves from memory (the file is read once) with an ETag + Content-Length, so
    repeated preview loads are a single 304 instead of a 4.6 MB transfer
  * handles each request on its own thread
  * swallows client disconnects instead of printing tracebacks
  * sets the headers the sandbox preview proxy needs (no X-Frame-Options /
    restrictive CSP; the page must be embeddable in an iframe)
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX = "index.html"


def load(path: str) -> tuple[bytes, str, str]:
    with open(path, "rb") as fh:
        body = fh.read()
    etag = '"%s"' % hashlib.sha1(body).hexdigest()[:16]
    return body, etag, mimetype(path)


def mimetype(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {
        ".html": "text/html; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".patch": "text/plain; charset=utf-8",
        ".png": "image/png",
    }.get(ext, "application/octet-stream")


class AtlasHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "AtlasExport/1.0"

    # set by the server
    cache: dict[str, tuple[bytes, str, str]] = {}

    def resolve(self) -> str | None:
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if path in ("/", ""):
            path = "/" + INDEX
        rel = os.path.normpath(path.lstrip("/"))
        if rel.startswith("..") or os.path.isabs(rel):
            return None
        full = os.path.join(ROOT, rel)
        if os.path.isdir(full):
            full = os.path.join(full, INDEX)
        return full if os.path.isfile(full) else None

    def do_GET(self) -> None:  # noqa: N802
        full = self.resolve()
        if full is None:
            self.send_error(HTTPStatus.NOT_FOUND, "not found")
            return
        entry = self.cache.get(full)
        if entry is None:
            try:
                entry = load(full)
            except OSError:
                self.send_error(HTTPStatus.NOT_FOUND, "not readable")
                return
            self.cache[full] = entry
        body, etag, ctype = entry

        if self.headers.get("If-None-Match") == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "no-cache")
        # the preview embeds this page in an iframe: keep it embeddable
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # browser navigated away / preview proxy cancelled

    def do_HEAD(self) -> None:  # noqa: N802
        full = self.resolve()
        if full is None:
            self.send_error(HTTPStatus.NOT_FOUND, "not found")
            return
        body, etag, ctype = self.cache.setdefault(full, load(full))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("ETag", etag)
        self.end_headers()

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[atlas] %s - %s\n" % (self.address_string(), fmt % args))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--bind", default="0.0.0.0")
    args = ap.parse_args()

    index = os.path.join(ROOT, INDEX)
    if not os.path.isfile(index):
        sys.exit("missing %s next to this script" % INDEX)

    httpd = ThreadingHTTPServer((args.bind, args.port), AtlasHandler)
    httpd.daemon_threads = True
    size = os.path.getsize(index)
    print(
        "[atlas] serving %s on http://%s:%d  (%s, %.2f MB, in-memory + ETag)"
        % (ROOT, args.bind, args.port, INDEX, size / 1024 / 1024),
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
