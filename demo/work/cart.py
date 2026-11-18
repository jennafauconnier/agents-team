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
