import { defineSample } from './build.ts'
import type { RowSpec } from './build.ts'

type Listing = [model: string, brand: string, priceInr: number, rating: number | null, inStock: boolean, sku: string]

const RETAILER: Record<'shopkart' | 'bazaarline' | 'electrohub', string> = {
  shopkart: 'ShopKart',
  bazaarline: 'BazaarLine',
  electrohub: 'ElectroHub',
}

const inr = (n: number) => `₹${n.toLocaleString('en-IN')}`

function listing(src: keyof typeof RETAILER, l: Listing, extra: Partial<RowSpec> = {}): RowSpec {
  const [model, brand, price, rating, inStock, sku] = l
  const structured = src === 'shopkart'
  return {
    src,
    path: `/p/${sku}`,
    ...extra,
    fields: {
      model: [model, structured ? `"name": "${model}"` : `${model} (8GB RAM, 128GB)`],
      brand: [brand, structured ? `"brand": { "name": "${brand}" }` : `Brand: ${brand}`],
      price_inr: [price, structured ? `"price": "${price}", "priceCurrency": "INR"` : `Deal price ${inr(price)}`],
      retailer: [RETAILER[src], `Sold by ${RETAILER[src]}`],
      rating: rating === null ? null : [rating, structured ? `"ratingValue": "${rating}"` : `${rating} out of 5 stars`],
      in_stock: [inStock, structured ? `"availability": "${inStock ? 'InStock' : 'OutOfStock'}"` : inStock ? 'In stock' : 'Currently unavailable'],
    },
  }
}

export const market = defineSample({
  key: 'market',
  label: 'Market prices',
  text: '5G smartphones under ₹20,000 from Indian retailers',
  rowLimit: 100,
  columns: [
    { key: 'model', label: 'Model', type: 'text', required: true },
    { key: 'brand', label: 'Brand', type: 'category', required: true },
    { key: 'price_inr', label: 'Price', type: 'money', required: true, currency: 'INR' },
    { key: 'retailer', label: 'Retailer', type: 'category', required: true },
    { key: 'rating', label: 'Rating', type: 'number', required: false },
    { key: 'in_stock', label: 'In stock', type: 'boolean', required: false },
  ],
  filters: [
    { column: 'price_inr', op: 'lte', value: 20000, label: 'Price up to ₹20,000' },
    { column: 'model', op: 'contains', value: '5G', label: 'Supports 5G' },
  ],
  interpretations: [
    {
      phrase: 'under ₹20,000',
      readAs: 'Current selling price up to ₹20,000, before bank offers',
      alternatives: ['Price after the best bank offer', 'List price (MRP) under ₹20,000'],
    },
    {
      phrase: 'Indian retailers',
      readAs: 'Online stores that ship across India',
      alternatives: ['Also include brand-owned stores'],
    },
  ],
  sources: [
    { id: 'shopkart', name: 'ShopKart', domain: 'shopkart.example', permission: 'allowed', method: 'structured', health: 'ok' },
    { id: 'bazaarline', name: 'BazaarLine', domain: 'bazaarline.example', permission: 'allowed', method: 'content', health: 'ok' },
    { id: 'electrohub', name: 'ElectroHub', domain: 'electrohub.example', permission: 'allowed', method: 'rendered', health: 'ok' },
    {
      id: 'pricewatch',
      name: 'PriceWatch',
      domain: 'pricewatch.example',
      permission: 'robots_disallowed',
      method: 'content',
      health: 'unknown',
      note: 'robots.txt disallows /product/ for automated agents.',
    },
  ],
  matchedOn: 'Same model at the same retailer',
  streamColumns: ['model', 'retailer', 'price_inr'],
  heroChart: 'price_inr',
  rows: [
    listing('shopkart', ['Orbit 5 Pro 5G', 'Orbit', 17999, 4.3, true, 'orbit-5-pro-5g']),
    listing('bazaarline', ['Orbit 5 Pro 5G', 'Orbit', 17499, 4.2, true, 'orbit-5-pro-5g']),
    listing('shopkart', ['Kestrel K12 5G', 'Kestrel', 12999, 4.1, true, 'kestrel-k12-5g']),
    listing('electrohub', ['Kestrel K12 5G', 'Kestrel', 13499, null, false, 'kestrel-k12-5g']),
    listing('shopkart', ['Veda V9 5G', 'Veda', 15999, 4.4, true, 'veda-v9-5g'], { also: ['bazaarline'] }),
    listing('bazaarline', ['Lumo Play 5G', 'Lumo', 11499, 3.9, true, 'lumo-play-5g']),
    listing('electrohub', ['Lumo Play Max 5G', 'Lumo', 14999, 4.0, true, 'lumo-play-max-5g']),
    listing('shopkart', ['Zephyr Z3 5G', 'Zephyr', 19499, 4.5, true, 'zephyr-z3-5g']),
    listing('bazaarline', ['Zephyr Z3 5G', 'Zephyr', 18999, 4.4, false, 'zephyr-z3-5g']),
    listing('electrohub', ['Orbit 5 Lite 5G', 'Orbit', 13999, 4.0, true, 'orbit-5-lite-5g']),
    listing('shopkart', ['Kestrel K12s 5G', 'Kestrel', 14499, 4.2, true, 'kestrel-k12s-5g'], {
      conflicts: { price_inr: { src: 'electrohub', path: '/p/kestrel-k12s-5g', value: 14999, quote: 'Deal price ₹14,999' } },
    }),
    listing('bazaarline', ['Veda V9 Neo 5G', 'Veda', 16499, 4.1, true, 'veda-v9-neo-5g']),
    listing('electrohub', ['Tarang T5 5G', 'Tarang', 10999, 3.8, true, 'tarang-t5-5g']),
    listing('shopkart', ['Tarang T7 5G', 'Tarang', 16999, 4.2, true, 'tarang-t7-5g'], { also: ['bazaarline'] }),
  ],
  rejected: [
    { sourceId: 'shopkart', label: 'Orbit 6 5G · ₹21,499', reason: 'Price over ₹20,000' },
    { sourceId: 'bazaarline', label: 'Lumo Play 4G · ₹8,999', reason: 'Does not support 5G' },
    { sourceId: 'electrohub', label: 'Veda V9 5G (refurbished)', reason: 'Refurbished listing, not new' },
  ],
})
