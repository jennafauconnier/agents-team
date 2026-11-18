const API = {
  async get(url) {
    const r = await fetch(url);
    return r.json();
  },
  async post(url, body) {
    const r = await fetch(url, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)
    });
    return r.json();
  }
};

let catalogCache = null;
async function getCatalog() {
  if (!catalogCache) catalogCache = (await API.get('/catalog'));
  return catalogCache;
}

function getState() {
  try { return JSON.parse(localStorage.getItem('cart') || '{}'); }
  catch { return {}; }
}

function setState(lines) {
  localStorage.setItem('cart', JSON.stringify(lines || {}));
}

// state attendu par le back : {"lines": {"A1":2,...}}
function stateToCart(lines) {
  return { lines: lines || {} };
}

// On conserve TOUTES les lignes (OK / STOCK_LOW / UNAVAILABLE)
// pour que update / remove puissent encore cibler un SKU indisponible.
function persistFromCart(cart, fallback) {
  const lines = {};
  for (const l of (cart?.lines || [])) {
    lines[l.sku] = l.qty;
  }
  // si le back a purgé une ligne (ex. remove), on part de l'état précédent
  // et on ne remet pas les SKU absents de la réponse
  setState(lines);
}

function updateCount(count) {
  const el = document.getElementById('cart-count');
  if (el) el.textContent = String(count ?? 0);
}

function toast(msg) {
  let el = document.getElementById('toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'toast';
    el.style.cssText = 'position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:#222;color:#fff;padding:8px 14px;border-radius:6px;font:14px sans-serif;opacity:0;transition:opacity .2s;z-index:1000;';
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.style.opacity = '1';
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.style.opacity = '0'; }, 1500);
}

async function addToCart(sku, qty = 1) {
  // ✅ envoie le state local pour que le back incrémente au lieu d'écraser
  const res = await API.post('/cart/add', {
    state: stateToCart(getState()),
    sku,
    qty
  });

  if (res.ok === false) {
    toast(res.error === 'OUT_OF_STOCK' ? 'Rupture de stock' : 'Erreur');
    return;
  }

  persistFromCart(res.cart);
  updateCount(res.cart?.count ?? 0);
  toast('Ajouté au panier');
}

// Réconciliation au chargement de n'importe quelle page (compteur fiable)
async function syncCount() {
  const res = await API.get('/cart?state=' + encodeURIComponent(JSON.stringify(stateToCart(getState()))));
  persistFromCart(res.cart);
  updateCount(res.cart?.count ?? 0);
  return res;
}

window.addEventListener('DOMContentLoaded', () => {
  const st = getState();
  updateCount(Object.values(st).reduce((a, b) => a + (Number(b) || 0), 0));
  syncCount().catch(() => {});
});
