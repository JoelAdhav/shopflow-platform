// All API calls go to /api/... on the same origin. nginx forwards them to the
// api container, so the browser never needs CORS.
const API = "/api";
let productNames = {};

function el(tag, text, className) {
  const node = document.createElement(tag);
  // textContent, never innerHTML: product names are user data (XSS safety).
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function showMessage(text, isError) {
  const box = document.getElementById("message");
  box.textContent = text;
  box.className = isError ? "error" : "ok";
}

async function loadProducts() {
  const products = await (await fetch(`${API}/products`)).json();
  const grid = document.getElementById("products");
  grid.replaceChildren();
  productNames = {};
  for (const p of products) {
    productNames[p.id] = p.name;
    const card = el("div", undefined, "card");
    card.append(
      el("h3", p.name),
      el("p", `$${(p.price_cents / 100).toFixed(2)}`, "price"),
      el("p", `${p.stock} in stock`, "stock"),
    );
    const button = el("button", p.stock > 0 ? "Order 1" : "Sold out");
    button.disabled = p.stock === 0;
    button.addEventListener("click", () => placeOrder(p.id));
    card.append(button);
    grid.append(card);
  }
}

async function loadOrders() {
  const orders = await (await fetch(`${API}/orders`)).json();
  const body = document.getElementById("orders");
  body.replaceChildren();
  for (const o of orders) {
    const row = el("tr");
    row.append(
      el("td", o.id),
      el("td", productNames[o.product_id] || `#${o.product_id}`),
      el("td", o.quantity),
      el("td", o.status, `status ${o.status}`),
      el("td", new Date(o.created_at).toLocaleTimeString()),
    );
    body.append(row);
  }
}

async function placeOrder(productId) {
  const res = await fetch(`${API}/orders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ product_id: productId, quantity: 1 }),
  });
  const data = await res.json();
  if (res.ok) {
    showMessage(`Order #${data.id} placed. The worker will process it.`, false);
  } else {
    showMessage(`Order failed: ${data.detail}`, true);
  }
  await refresh();
}

async function refresh() {
  const badge = document.getElementById("api-status");
  try {
    await loadProducts();
    await loadOrders();
    badge.textContent = "api up";
    badge.className = "badge up";
  } catch (err) {
    badge.textContent = "api down";
    badge.className = "badge down";
  }
}

refresh();
setInterval(refresh, 2000);
