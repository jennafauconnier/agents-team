## API

Contrat d'échange (JSON). Le back expose des **fonctions**, un petit adaptateur `http.server` fait le mapping HTTP → fonction. Pas de framework.

| Endpoint | Entrée | Sortie |
|---|---|---|
| `POST /cart/add` | `{"sku":"A1","qty":1}` | `{"cart": {...}, "ok": true}` ou `{"ok": false, "error":"OUT_OF_STOCK"}` |
| `GET /cart?state=<json>` | `state` = panier local (URL-encoded) | `{"cart": {...}, "warnings":[...]}` |
| `POST /cart/update` | `{"state":{...},"sku":"A1","qty":3}` | `{"cart": {...}, "warnings":[...], "ok":true}` |
| `POST /cart/remove` | `{"state":{...},"sku":"A1"}` | `{"cart": {...}, "warnings":[]}` |
| `GET /catalog` | — | `{"A1":{"name":"...","price":9.9,"stock":5,"active":true}, ...}` |

**Formats**

```json
// state / cart
{"lines": {"A1": 2, "A2": 1}}

// réconcilié (retour GET /cart, update, remove)
{
  "lines": [
    {"sku":"A1","name":"Câble","price":9.9,"qty":2,"line_total":19.8,
     "status":"OK","stock":5}
  ],
  "subtotal": 19.8,
  "count": 2
}

// warnings
[{"sku":"A2","code":"UNAVAILABLE","msg":"Article indisponible"},
 {"sku":"A1","code":"STOCK_LOW","msg":"Stock disponible : 3","max":3}]
```

`count` = somme des qty des lignes `status == "OK"` uniquement.  
Lignes `UNAVAILABLE` gardées en `lines` (pour affichage + suppression), exclues de `subtotal`/`count`.

---

## FRONT

- `localStorage['cart']` = `{"A1":2,...}` → source de vérité, envoyé en `state` à chaque appel.
- `catalog` fetché au chargement, mis en cache mémoire.
- **Fiche produit** : si `stock === 0 || !active` → bouton `disabled` + message « Indisponible ». Sinon clic → `POST /cart/add`, merge réponse dans `localStorage`, update compteur header + toast confirmation.
- **Header** : `<span id="cart-count">`, recalculé depuis la dernière réponse `cart.count`, liens vers `cart.html`.
- `cart.html` : au load → `GET /cart?state=...` → rendu des lignes (nom, PU, qty, sous-total), `subtotal`, état vide si `lines.length === 0`.
- Ligne `UNAVAILABLE` / `STOCK_LOW` : badge message, input qty `max = stock` si `STOCK_LOW`, bouton « Supprimer » toujours présent.
- `change` qty → `POST /cart/update` ; clic supprimer → `POST /cart/remove` → re-render + `localStorage` + compteur.
- Pas de router, pas de build, 2 fichiers : `product.html`, `cart.html` + `app.js` partagé.

---

## BACK

- `catalog.py` : dict en mémoire `{sku: {"name","price","stock","active"}}` + `get_catalog()`.
- `cart.py` :
  - `reconcile(state: dict, catalog) -> dict` : pour chaque sku → `OK` / `UNAVAILABLE` / `STOCK_LOW`, calcule `line_total`, `subtotal`, `count`, `warnings`.
  - `add(state, sku, qty, catalog) -> (state, ok, error)` : refuse si indispo ou `qty > stock`, sinon incrémente sans doublon.
  - `update(state, sku, qty, catalog) -> state` : `qty<=0` ⇒ suppression, sinon clamp au stock.
  - `remove(state, sku) -> state`.
- `server.py` : `http.server.BaseHTTPRequestHandler`, parse `json` du body / query, appelle les fonctions, renvoie `application/json` + `200`/`400`. Rien d'autre.
- Prix en `float` arrondi à 2 décimales au calcul de `subtotal`. Pas de session, pas de DB, pas d'auth (MVP).

---

**Décision TL** : l'état reste côté navigateur, le back est *stateless* et fait autorité sur le catalogue/stock. C'est le minimum pour couvrir CA3 de la Story 3 sans introduire de persistance serveur. On branche une vraie session seulement si le PO demande le panier multi-device.