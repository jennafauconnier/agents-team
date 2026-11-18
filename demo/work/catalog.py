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
