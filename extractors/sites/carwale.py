"""CarWale listing extraction via live DOM."""

from __future__ import annotations

from playwright.sync_api import Page

_EVAL = """
() => {
  const rows = [];
  const seen = new Set();
  const push = (model, price, brand) => {
    model = (model || '').replace(/\\s+/g, ' ').trim();
    price = (price || '').replace(/\\s+/g, ' ').trim();
    brand = (brand || '').replace(/\\s+/g, ' ').trim();
    if (!model || !/[a-zA-Z]{2}/.test(model)) return;
    if (!price || !/\\d/.test(price)) return;
    if (/recommended|priced from|under rs/i.test(model)) return;
    const key = model + '|' + price;
    if (seen.has(key)) return;
    seen.add(key);
    rows.push({ brand, model, ex_showroom_price: price });
  };

  const priceRe = /(Rs\\.?\\s*[\\d,.]+\\s*(?:-\\s*[\\d,.]+)?\\s*(?:Lakh|lac)?|₹[\\d,.]+)/i;

  document.querySelectorAll('[data-testing-id="model-name"], h3, .o-jc-card-title, [class*="model-name"]').forEach(nameEl => {
    const card = nameEl.closest('[data-testing-id="make-model-card"], li, article, div[class*="card"]') || nameEl.parentElement;
    if (!card) return;
    const model = nameEl.textContent.trim();
    const priceEl = card.querySelector('[class*="price" i], [data-testing-id*="price"]');
    let price = priceEl ? priceEl.textContent.trim() : '';
    if (!price) {
      const m = (card.textContent || '').match(priceRe);
      price = m ? m[0] : '';
    }
    push(model, price, '');
  });

  document.querySelectorAll('a[href*="/new/"], a[href*="/electric-cars/"]').forEach(a => {
    const href = a.getAttribute('href') || '';
    if (!/\\/new\\/[a-z0-9-]+\\//i.test(href) && !href.includes('cars')) return;
    const card = a.closest('li, div[class*="card"], article') || a.parentElement;
    if (!card) return;
    const model = a.textContent.trim();
    if (model.length < 3 || model.length > 80) return;
    const m = (card.textContent || '').match(priceRe);
    if (m) push(model, m[0], '');
  });

  return rows;
}
"""


def extract_page(page: Page) -> list[dict[str, str]]:
    return page.evaluate(_EVAL)
