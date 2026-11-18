### FILE: app.js
```js
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
```

### FILE: product.html
```html
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Produit</title>
<style>
  body{font:16px system-ui,sans-serif;margin:0;padding:0;background:#fafafa}
  header{display:flex;justify-content:space-between;align-items:center;padding:12px 20px;background:#fff;border-bottom:1px solid #eee}
  header a{color:#333;text-decoration:none;font-weight:600}
  main{max-width:640px;margin:24px auto;padding:0 16px}
  .card{background:#fff;border:1px solid #eee;border-radius:8px;padding:20px;display:flex;flex-direction:column;gap:12px}
  h1{margin:0;font-size:22px}
  .price{font-size:20px;font-weight:700;color:#0b7}
  .stock{font-size:14px;color:#666}
  button{padding:10px 16px;border:none;border-radius:6px;background:#0b7;color:#fff;font:inherit;cursor:pointer}
  button:disabled{background:#ccc;cursor:not-allowed}
  .unavail{color:#c33;font-weight:600}
</style>
</head>
<body>
<header>
  <a href="product.html">Boutique</a>
  <a href="cart.html">Panier (<span id="cart-count">0</span>)</a>
</header>
<main>
  <div class="card" id="product">Chargement…</div>
</main>
<script src="app.js"></script>
<script>
(async () => {
  const sku = new URLSearchParams(location.search).get('sku') || 'A1';
  const catalog = await getCatalog();
  const p = catalog[sku];
  const root = document.getElementById('product');
  if (!p) { root.textContent = 'Produit introuvable'; return; }

  const available = p.active && p.stock > 0;
  root.innerHTML = `
    <h1>${p.name}</h1>
    <div class="price">${p.price.toFixed(2)} €</div>
    <div class="stock">${available ? 'Stock : ' + p.stock : '<span class="unavail">Indisponible</span>'}</div>
  `;

  const btn = document.createElement('button');
  btn.textContent = available ? 'Ajouter au panier' : 'Indisponible';
  if (!available) {
    btn.disabled = true;
  } else {
    btn.addEventListener('click', () => addToCart(sku, 1));
  }
  root.appendChild(btn);
})();
</script>
</body>
</html>
```

### FILE: cart.html
```html
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Panier</title>
<style>
  body{font:16px system-ui,sans-serif;margin:0;padding:0;background:#fafafa}
  header{display:flex;justify-content:space-between;align-items:center;padding:12px 20px;background:#fff;border-bottom:1px solid #eee}
  header a{color:#333;text-decoration:none;font-weight:600}
  main{max-width:760px;margin:24px auto;padding:0 16px}
  .empty{padding:40px;text-align:center;color:#888;background:#fff;border:1px solid #eee;border-radius:8px}
  .lines{background:#fff;border:1px solid #eee;border-radius:8px;overflow:hidden}
  .line{display:grid;grid-template-columns:1fr auto auto auto;gap:12px;align-items:center;padding:12px 16px;border-bottom:1px solid #f0f0f0}
  .line:last-child{border-bottom:none}
  .name{font-weight:600}
  .price{color:#666;font-size:14px}
  .badge{display:inline-block;font-size:12px;padding:2px 8px;border-radius:10px;margin-top:4px}
  .badge.warn{background:#fff3cd;color:#856404}
  .badge.err{background:#f8d7da;color:#721c24}
  input[type=number]{width:60px;padding:6px;border:1px solid #ddd;border-radius:4px;font:inherit}
  button{padding:8px 12px;border:none;border-radius:6px;background:#eee;color:#333;font:inherit;cursor:pointer}
  button.danger{background:#f8d7da;color:#721c24}
  .totals{margin-top:16px;padding:16px;background:#fff;border:1px solid #eee;border-radius:8px;display:flex;justify-content:space-between;font-size:18px;font-weight:700}
</style>
</head>
<body>
<header>
  <a href="product.html">Boutique</a>
  <a href="cart.html">Panier (<span id="cart-count">0</span>)</a>
</header>
<main id="root">Chargement…</main>
<script src="app.js"></script>
<script>
function render(cart, warnings) {
  const root = document.getElementById('root');
  const wz = {};
  for (const w of (warnings || [])) (wz[w.sku] ||= []).push(w);

  if (!cart || !cart.lines || cart.lines.length === 0) {
    root.innerHTML = '<div class="empty">Votre panier est vide.</div>';
    updateCount(0);
    return;
  }

  const rows = cart.lines.map(l => {
    const ws = wz[l.sku] || [];
    const low = ws.find(w => w.code === 'STOCK_LOW');
    const badges = ws.map(w => {
      const cls = w.code === 'UNAVAILABLE' ? 'err' : 'warn';
      return `<div class="badge ${cls}">${w.msg}</div>`;
    }).join('');

    // STOCK_LOW → max = stock ; UNAVAILABLE → qty figée, mais Supprimer reste actif
    const maxAttr = low && typeof low.max === 'number' ? `max="${low.max}"` : '';
    const disabled = l.status === 'UNAVAILABLE' ? 'disabled' : '';

    return `
      <div class="line" data-sku="${l.sku}">
        <div>
          <div class="name">${l.name}</div>
          <div class="price">${l.price.toFixed(2)} € / unité</div>
          ${badges}
        </div>
        <input type="number" min="1" ${maxAttr} ${disabled} value="${l.qty}" data-role="qty">
        <div class="price">${l.line_total.toFixed(2)} €</div>
        <button class="danger" data-role="del">Supprimer</button>
      </div>`;
  }).join('');

  root.innerHTML = `
    <div class="lines">${rows}</div>
    <div class="totals">
      <span>Total (${cart.count} art.)</span>
      <span>${cart.subtotal.toFixed(2)} €</span>
    </div>`;

  updateCount(cart.count);

  root.querySelectorAll('.line').forEach(el => {
    const sku = el.dataset.sku;
    el.querySelector('[data-role=qty]')?.addEventListener('change', async e => {
      const input = e.target;
      const max = input.max ? Number(input.max) : Infinity;
      let qty = Math.max(1, parseInt(input.value, 10) || 1);
      if (qty > max) { qty = max; input.value = max; }
      await doUpdate(sku, qty);
    });
    el.querySelector('[data-role=del]')?.addEventListener('click', () => doRemove(sku));
  });
}

async function load() {
  const res = await syncCount();           // GET /cart?state=... + persist complet
  render(res.cart, res.warnings || []);
}

async function doUpdate(sku, qty) {
  // ✅ state contient encore les lignes UNAVAILABLE / STOCK_LOW
  const res = await API.post('/cart/update', {
    state: stateToCart(getState()),
    sku,
    qty
  });
  persistFromCart(res.cart);
  updateCount(res.cart?.count ?? 0);
  render(res.cart, res.warnings || []);
}

async function doRemove(sku) {
  // ✅ la ligne indisponible est toujours présente dans le state envoyé
  const res = await API.post('/cart/remove', {
    state: stateToCart(getState()),
    sku
  });
  persistFromCart(res.cart);
  updateCount(res.cart?.count ?? 0);
  render(res.cart, res.warnings || []);
}

load().catch(() => {
  document.getElementById('root').innerHTML = '<div class="empty">Erreur de chargement.</div>';
});
</script>
</body>
</html>
```