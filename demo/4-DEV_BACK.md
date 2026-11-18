### FILE: catalog.py
```python
"""Catalogue en mémoire (source de vérité : prix & stock)."""

CATALOG = {
    "A1": {"name": "Câble USB-C", "price": 9.9, "stock": 5, "active": True},
    "A2": {"name": "Adaptateur HDMI", "price": 19.9, "stock": 0, "active": True},
    "A3": {"name": "Souris sans fil", "price": 24.5, "stock": 3, "active": True},
    "A4": {"name": "Clavier mécanique", "price": 89.0, "stock": 2, "active": False},
    "A5": {"name": "Hub USB 4 ports", "price": 15.0, "stock": 10, "active": True},
}


def get_catalog() -> dict:
    """Retourne le catalogue (copie superficielle suffisante pour lecture)."""
    return CATALOG
```

### FILE: cart.py
```python
"""Logique panier — stateless, autorité catalogue côté back."""
from typing import Tuple

from catalog import get_catalog


def _lookup(catalog: dict, sku: str):
    item = catalog.get(sku)
    if not item or not item.get("active"):
        return None
    return item


def reconcile(state: dict, catalog: dict = None) -> dict:
    """Réconcilie un state {lines:{sku:qty}} contre le catalogue.

    Retourne {"lines":[...], "subtotal": float, "count": int, "warnings":[...]}.
    """
    catalog = catalog if catalog is not None else get_catalog()
    raw = state.get("lines", {}) if isinstance(state, dict) else {}
    lines_out = []
    warnings = []
    subtotal = 0.0
    count = 0

    for sku, qty in raw.items():
        try:
            qty = int(qty)
        except (TypeError, ValueError):
            qty = 0
        if qty <= 0:
            continue

        item = _lookup(catalog, sku)
        if item is None:
            line = {
                "sku": sku,
                "name": None,
                "price": None,
                "qty": qty,
                "line_total": 0.0,
                "status": "UNAVAILABLE",
                "stock": 0,
            }
            warnings.append({"sku": sku, "code": "UNAVAILABLE", "msg": "Article indisponible"})
            lines_out.append(line)
            continue

        stock = int(item["stock"])
        price = float(item["price"])
        if stock <= 0:
            line = {
                "sku": sku,
                "name": item["name"],
                "price": price,
                "qty": qty,
                "line_total": 0.0,
                "status": "UNAVAILABLE",
                "stock": 0,
            }
            warnings.append({"sku": sku, "code": "UNAVAILABLE", "msg": "Article indisponible"})
            lines_out.append(line)
            continue

        if qty > stock:
            line_qty = stock
            line = {
                "sku": sku,
                "name": item["name"],
                "price": price,
                "qty": line_qty,
                "line_total": round(price * line_qty, 2),
                "status": "STOCK_LOW",
                "stock": stock,
            }
            warnings.append(
                {"sku": sku, "code": "STOCK_LOW", "msg": f"Stock disponible : {stock}", "max": stock}
            )
        else:
            line_qty = qty
            line = {
                "sku": sku,
                "name": item["name"],
                "price": price,
                "qty": line_qty,
                "line_total": round(price * line_qty, 2),
                "status": "OK",
                "stock": stock,
            }

        lines_out.append(line)
        subtotal += line["line_total"]
        count += line_qty

    return {
        "lines": lines_out,
        "subtotal": round(subtotal, 2),
        "count": count,
        "warnings": warnings,
    }


def add(state: dict, sku: str, qty: int, catalog: dict = None) -> Tuple[dict, bool, str]:
    """Incrémente la quantité existante sans doublon. Refuse si indispo ou dépassement stock."""
    catalog = catalog if catalog is not None else get_catalog()
    item = catalog.get(sku)
    if not item or not item.get("active") or int(item.get("stock", 0)) <= 0:
        return state, False, "OUT_OF_STOCK"

    try:
        qty = int(qty)
    except (TypeError, ValueError):
        return state, False, "INVALID_QTY"
    if qty <= 0:
        return state, False, "INVALID_QTY"

    stock = int(item["stock"])
    current = int(state.get("lines", {}).get(sku, 0))
    target = current + qty
    if target > stock:
        return state, False, "OUT_OF_STOCK"

    new_state = {"lines": dict(state.get("lines", {}))}
    new_state["lines"][sku] = target
    return new_state, True, ""


def update(state: dict, sku: str, qty: int, catalog: dict = None) -> dict:
    """qty<=0 => suppression ; sinon clamp au stock (garde la ligne si indispo)."""
    catalog = catalog if catalog is not None else get_catalog()
    lines = dict(state.get("lines", {}))

    try:
        qty = int(qty)
    except (TypeError, ValueError):
        qty = 0

    if qty <= 0:
        lines.pop(sku, None)
        return {"lines": lines}

    item = catalog.get(sku)
    if not item or not item.get("active"):
        lines[sku] = qty
        return {"lines": lines}

    stock = int(item.get("stock", 0))
    if stock <= 0:
        lines[sku] = qty
        return {"lines": lines}

    clamped = max(0, min(qty, stock))
    if clamped <= 0:
        lines.pop(sku, None)
    else:
        lines[sku] = clamped
    return {"lines": lines}


def remove(state: dict, sku: str) -> dict:
    lines = dict(state.get("lines", {}))
    lines.pop(sku, None)
    return {"lines": lines}
```

### FILE: server.py
```python
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
```

### FILE: test_cart.py
```python
import unittest

from catalog import get_catalog
from cart import reconcile, add, update, remove


def _cat():
    return get_catalog()


class TestReconcile(unittest.TestCase):
    def test_empty(self):
        r = reconcile({"lines": {}}, _cat())
        self.assertEqual(r["lines"], [])
        self.assertEqual(r["subtotal"], 0.0)
        self.assertEqual(r["count"], 0)
        self.assertEqual(r["warnings"], [])

    def test_ok(self):
        r = reconcile({"lines": {"A1": 2, "A5": 1}}, _cat())
        skus = {l["sku"]: l for l in r["lines"]}
        self.assertEqual(skus["A1"]["status"], "OK")
        self.assertEqual(skus["A1"]["line_total"], 19.8)
        self.assertEqual(skus["A5"]["status"], "OK")
        self.assertEqual(skus["A5"]["line_total"], 15.0)
        self.assertEqual(r["subtotal"], 34.8)
        self.assertEqual(r["count"], 3)
        self.assertEqual(r["warnings"], [])

    def test_stock_low(self):
        r = reconcile({"lines": {"A1": 10}}, _cat())
        line = r["lines"][0]
        self.assertEqual(line["status"], "STOCK_LOW")
        self.assertEqual(line["qty"], 5)
        self.assertEqual(line["line_total"], 49.5)
        self.assertEqual(r["count"], 5)
        self.assertEqual(r["subtotal"], 49.5)
        self.assertEqual(len(r["warnings"]), 1)
        w = r["warnings"][0]
        self.assertEqual(w["code"], "STOCK_LOW")
        self.assertEqual(w["sku"], "A1")
        self.assertEqual(w["max"], 5)

    def test_unavailable_unknown_sku(self):
        r = reconcile({"lines": {"ZZ": 1}}, _cat())
        self.assertEqual(r["lines"][0]["status"], "UNAVAILABLE")
        self.assertEqual(r["subtotal"], 0.0)
        self.assertEqual(r["count"], 0)
        self.assertEqual(r["warnings"][0]["code"], "UNAVAILABLE")

    def test_unavailable_inactive(self):
        r = reconcile({"lines": {"A4": 1}}, _cat())
        self.assertEqual(r["lines"][0]["status"], "UNAVAILABLE")
        self.assertEqual(r["subtotal"], 0.0)
        self.assertEqual(r["count"], 0)

    def test_unavailable_stock_zero(self):
        r = reconcile({"lines": {"A2": 1}}, _cat())
        self.assertEqual(r["lines"][0]["status"], "UNAVAILABLE")
        self.assertEqual(r["count"], 0)

    def test_count_excludes_unavailable(self):
        r = reconcile({"lines": {"A1": 1, "A2": 2, "A5": 3}}, _cat())
        self.assertEqual(r["count"], 4)  # A1 qty=1 + A5 qty=3
        self.assertAlmostEqual(r["subtotal"], round(9.9 + 45.0, 2))

    def test_subtotal_rounding(self):
        r = reconcile({"lines": {"A3": 1}}, _cat())
        self.assertEqual(r["subtotal"], 24.5)


class TestAdd(unittest.TestCase):
    def test_add_new(self):
        state, ok, err = add({"lines": {}}, "A1", 2, _cat())
        self.assertTrue(ok)
        self.assertEqual(state, {"lines": {"A1": 2}})
        self.assertEqual(err, "")

    def test_add_accumulates(self):
        """Story 1 CA2 : ajout sur une ligne existante incrément la quantité."""
        state, ok, err = add({"lines": {"A1": 1}}, "A1", 1, _cat())
        self.assertTrue(ok)
        self.assertEqual(state["lines"], {"A1": 2})

    def test_add_accumulates_multiple_times(self):
        state = {"lines": {}}
        state, ok, _ = add(state, "A1", 2, _cat())
        self.assertTrue(ok)
        self.assertEqual(state["lines"], {"A1": 2})
        state, ok, _ = add(state, "A1", 3, _cat())
        self.assertTrue(ok)
        self.assertEqual(state["lines"], {"A1": 5})

    def test_add_accumulates_exceeds_stock(self):
        """L'accumulation qui dépasse le stock est refusée et l'état est inchangé."""
        state = {"lines": {"A1": 4}}
        new_state, ok, err = add(state, "A1", 2, _cat())
        self.assertFalse(ok)
        self.assertEqual(err, "OUT_OF_STOCK")
        self.assertEqual(new_state, {"lines": {"A1": 4}})

    def test_add_out_of_stock(self):
        state, ok, err = add({"lines": {}}, "A1", 6, _cat())
        self.assertFalse(ok)
        self.assertEqual(err, "OUT_OF_STOCK")

    def test_add_inactive(self):
        _, ok, err = add({"lines": {}}, "A4", 1, _cat())
        self.assertFalse(ok)
        self.assertEqual(err, "OUT_OF_STOCK")

    def test_add_unknown(self):
        _, ok, err = add({"lines": {}}, "ZZ", 1, _cat())
        self.assertFalse(ok)
        self.assertEqual(err, "OUT_OF_STOCK")

    def test_add_invalid_qty(self):
        _, ok, err = add({"lines": {}}, "A1", "x", _cat())
        self.assertFalse(ok)
        self.assertEqual(err, "INVALID_QTY")

    def test_add_zero_qty(self):
        _, ok, err = add({"lines": {}}, "A1", 0, _cat())
        self.assertFalse(ok)
        self.assertEqual(err, "INVALID_QTY")

    def test_add_negative_qty(self):
        _, ok, err = add({"lines": {}}, "A1", -1, _cat())
        self.assertFalse(ok)
        self.assertEqual(err, "INVALID_QTY")


class TestUpdate(unittest.TestCase):
    def test_update_clamp(self):
        state = update({"lines": {"A1": 1}}, "A1", 99, _cat())
        self.assertEqual(state["lines"]["A1"], 5)

    def test_update_zero_removes(self):
        state = update({"lines": {"A1": 2}}, "A1", 0, _cat())
        self.assertNotIn("A1", state["lines"])

    def test_update_new_line(self):
        state = update({"lines": {}}, "A3", 2, _cat())
        self.assertEqual(state["lines"]["A3"], 2)

    def test_update_unavailable_keeps_line(self):
        """Une ligne indisponible est conservée dans le state pour affichage/suppression."""
        state = update({"lines": {}}, "A2", 1, _cat())
        self.assertEqual(state["lines"], {"A2": 1})

    def test_update_negative_removes(self):
        state = update({"lines": {"A1": 2}}, "A1", -1, _cat())
        self.assertNotIn("A1", state["lines"])


class TestRemove(unittest.TestCase):
    def test_remove(self):
        state = remove({"lines": {"A1": 2, "A5": 1}}, "A1")
        self.assertEqual(state["lines"], {"A5": 1})

    def test_remove_missing(self):
        state = remove({"lines": {"A5": 1}}, "ZZ")
        self.assertEqual(state["lines"], {"A5": 1})


class TestIntegration(unittest.TestCase):
    def test_flow(self):
        state = {"lines": {}}
        state, ok, _ = add(state, "A1", 2, _cat())
        self.assertTrue(ok)
        state, ok, _ = add(state, "A3", 1, _cat())
        self.assertTrue(ok)

        r = reconcile(state, _cat())
        self.assertEqual(r["count"], 3)
        self.assertAlmostEqual(r["subtotal"], round(9.9 * 2 + 24.5, 2))

        state = update(state, "A3", 99, _cat())
        self.assertEqual(state["lines"]["A3"], 3)

        r = reconcile(state, _cat())
        self.assertEqual(r["count"], 5)
        self.assertAlmostEqual(r["subtotal"], round(9.9 * 2 + 24.5 * 3, 2))

        state = remove(state, "A1")
        r = reconcile(state, _cat())
        self.assertEqual(r["count"], 3)
        self.assertAlmostEqual(r["subtotal"], round(24.5 * 3, 2))

    def test_flow_with_accumulation(self):
        """Story 1 CA2 : add successifs accumulent, le panier grandit correctement."""
        state = {"lines": {}}
        state, ok, _ = add(state, "A5", 3, _cat())
        self.assertTrue(ok)
        state, ok, _ = add(state, "A5", 2, _cat())
        self.assertTrue(ok)
        self.assertEqual(state["lines"], {"A5": 5})

        r = reconcile(state, _cat())
        self.assertEqual(r["count"], 5)
        self.assertEqual(r["subtotal"], 75.0)

    def test_flow_state_preserved_on_add(self):
        """Story 1 CA1/CA2 : le state est envoyé et préservé d'un appel add à l'autre."""
        state = {"lines": {}}
        state, ok, _ = add(state, "A1", 2, _cat())
        self.assertTrue(ok)
        state, ok, _ = add(state, "A3", 1, _cat())
        self.assertTrue(ok)
        self.assertEqual(state["lines"], {"A1": 2, "A3": 1})

        r = reconcile(state, _cat())
        self.assertEqual(r["count"], 3)
        self.assertAlmostEqual(r["subtotal"], round(9.9 * 2 + 24.5, 2))

    def test_unavailable_line_remains_in_state(self):
        """Story 3 CA2 : une ligne UNAVAILABLE reste dans le state pour suppression."""
        state = {"lines": {"A2": 1, "A1": 2}}
        r = reconcile(state, _cat())
        self.assertEqual(r["count"], 2)
        self.assertAlmostEqual(r["subtotal"], 19.8)
        # A2 est bien présent
        skus = [l["sku"] for l in r["lines"]]
        self.assertIn("A2", skus)
        self.assertIn("A1", skus)
        # suppression possible
        state = remove(state, "A2")
        self.assertNotIn("A2", state["lines"])
        self.assertIn("A1", state["lines"])


if __name__ == "__main__":
    unittest.main()
```