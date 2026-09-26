"""CarDekho listing extraction via live DOM."""

from __future__ import annotations

from playwright.sync_api import Page

_EVAL = """
() => {
  const rows = [];
  const seen = new Set();
  const push = (model, price, brand, rangeKm) => {
    model = (model || '').replace(/\\s+/g, ' ').trim();
    price = (price || '').replace(/\\s+/g, ' ').trim();
    brand = (brand || '').replace(/\\s+/g, ' ').trim();
    rangeKm = (rangeKm || '').replace(/\\s+/g, ' ').trim();
    if (!model || model.length < 2) return;
    if (!/[a-zA-Z]/.test(model)) return;
    if (!price && !rangeKm) return;
    const key = model + '|' + price;
    if (seen.has(key)) return;
    seen.add(key);
    rows.push({
      brand,
      model,
      ex_showroom_price: price,
      range: rangeKm,
    });
  };

  const priceRe = /(₹[\\d,.]+|[\\d.]+\\s*[-–*\\s]*[\\d.]*)\\s*(Lakh|lac|Cr)?/i;

  document.querySelectorAll('li[data-price], li.gsc_col-xs-12, div[data-model]').forEach(el => {
    const modelEl = el.querySelector('h3, h2, [class*="title"], a[title]');
    let model = modelEl ? (modelEl.getAttribute('title') || modelEl.textContent) : '';
    const priceEl = el.querySelector('[class*="price" i], .price, span[data-price]');
    let price = priceEl ? priceEl.textContent : '';
    if (!price) {
      const m = (el.textContent || '').match(priceRe);
      if (m) price = m[0];
    }
    const brandEl = el.querySelector('[class*="brand" i], .brandName');
    const brand = brandEl ? brandEl.textContent : '';
    const rangeEl = el.querySelector('[class*="range" i], [class*="Range"]');
    push(model, price, brand, rangeEl ? rangeEl.textContent : '');
  });

  document.querySelectorAll('table tr').forEach((tr, idx) => {
    if (idx === 0) return;
    const cells = [...tr.querySelectorAll('td, th')].map(c => c.textContent.trim());
    if (cells.length >= 2) push(cells[0], cells[1], cells.length > 2 ? cells[2] : '', '');
  });

  document.querySelectorAll('a[href*="/car/"], a[href*="/carmodels/"]').forEach(a => {
    const card = a.closest('li, article, div[class*="card"], div[class*="Car"]') || a.parentElement;
    if (!card) return;
    const model = (a.getAttribute('title') || a.textContent || '').trim();
    const blob = card.textContent || '';
    const pm = blob.match(priceRe);
    push(model, pm ? pm[0] : '', '', '');
  });

  return rows;
}
"""


def extract_page(page: Page) -> list[dict[str, str]]:
    return page.evaluate(_EVAL)
