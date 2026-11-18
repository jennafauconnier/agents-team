"""Adaptateur HTTP minimal (http.server) — mapping endpoint → fonction."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from catalog import get_catalog
from cart import add, update, remove, reconcile


def _json_response(handler, payload, status=200):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler):
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if length <= 0:
        return None
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def _parse_state_param(query) -> dict:
    raw = parse_qs(query).get("state", [None])[0]
    if not raw:
        return {"lines": {}}
    try:
        state = json.loads(raw)
        if not isinstance(state, dict):
            return {"lines": {}}
        return state
    except json.JSONDecodeError:
        return {"lines": {}}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _dispatch_get(self, path, query):
        if path == "/catalog":
            return _json_response(self, get_catalog())
        if path == "/cart":
            state = _parse_state_param(query)
            cart = reconcile(state)
            return _json_response(self, {"cart": cart, "warnings": cart["warnings"]})
        return _json_response(self, {"ok": False, "error": "NOT_FOUND"}, 400)

    def _dispatch_post(self, path, body):
        if not isinstance(body, dict):
            return _json_response(self, {"ok": False, "error": "INVALID_BODY"}, 400)

        if path == "/cart/add":
            state = body.get("state") or {"lines": {}}
            sku = body.get("sku")
            qty = body.get("qty", 1)
            new_state, ok, error = add(state, sku, qty)
            if not ok:
                return _json_response(self, {"ok": False, "error": error}, 400)
            cart = reconcile(new_state)
            return _json_response(self, {"cart": cart, "warnings": cart["warnings"], "ok": True})

        if path == "/cart/update":
            state = body.get("state") or {"lines": {}}
            sku = body.get("sku")
            qty = body.get("qty", 0)
            new_state = update(state, sku, qty)
            cart = reconcile(new_state)
            return _json_response(self, {"cart": cart, "warnings": cart["warnings"], "ok": True})

        if path == "/cart/remove":
            state = body.get("state") or {"lines": {}}
            sku = body.get("sku")
            new_state = remove(state, sku)
            cart = reconcile(new_state)
            return _json_response(self, {"cart": cart, "warnings": cart["warnings"]})

        return _json_response(self, {"ok": False, "error": "NOT_FOUND"}, 400)

    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            self._dispatch_get(parsed.path, parsed.query)
        except Exception:
            _json_response(self, {"ok": False, "error": "INTERNAL"}, 400)

    def do_POST(self):
        parsed = urlparse(self.path)
        body = _read_json(self)
        try:
            self._dispatch_post(parsed.path, body)
        except Exception:
            _json_response(self, {"ok": False, "error": "INTERNAL"}, 400)


def make_server(host="127.0.0.1", port=8000):
    return HTTPServer((host, port), Handler)


if __name__ == "__main__":
    print("Listening on http://127.0.0.1:8000")
    make_server().serve_forever()
