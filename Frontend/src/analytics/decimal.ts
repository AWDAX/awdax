/**
 * Exact decimals: `n / 10^s` with a BigInt numerator. Sums, differences and products are exact, so a
 * total over 10,000 scraped prices matches the source to the last paisa; floating point would drift
 * (0.1 + 0.2). Division rounds half-to-even at a stated scale, so every rounding is a choice we can name.
 * Floats appear only in toNumber(), for chart geometry.
 */
export interface Dec {
  readonly n: bigint
  readonly s: number
}

const TEN = 10n
const pow10 = (k: number): bigint => TEN ** BigInt(k)

export const ZERO: Dec = { n: 0n, s: 0 }

/** From a canonical decimal string: optional sign, digits, optional fraction ("-12.340"). */
export function fromString(str: string): Dec | null {
  const m = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(str.trim())
  if (!m) return null
  const frac = m[3] ?? ''
  const n = BigInt(m[2] + frac) * (m[1] === '-' ? -1n : 1n)
  return normalize({ n, s: frac.length })
}

export function fromInt(i: number | bigint): Dec {
  return { n: BigInt(i), s: 0 }
}

/** Drops trailing zeros in the fraction: 12.500 → 12.5. Scale never goes below 0. */
export function normalize(d: Dec): Dec {
  let { n, s } = d
  while (s > 0 && n % TEN === 0n) {
    n /= TEN
    s -= 1
  }
  return { n, s }
}

function align(a: Dec, b: Dec): [bigint, bigint, number] {
  const s = Math.max(a.s, b.s)
  return [a.n * pow10(s - a.s), b.n * pow10(s - b.s), s]
}

export function add(a: Dec, b: Dec): Dec {
  const [x, y, s] = align(a, b)
  return normalize({ n: x + y, s })
}

export function sub(a: Dec, b: Dec): Dec {
  const [x, y, s] = align(a, b)
  return normalize({ n: x - y, s })
}

export function mul(a: Dec, b: Dec): Dec {
  return normalize({ n: a.n * b.n, s: a.s + b.s })
}

/** Multiplies by 10^k exactly (k may be negative): for "lakh", "crore", "M". */
export function shift(a: Dec, k: number): Dec {
  if (k >= 0) return normalize({ n: a.n * pow10(k), s: a.s })
  return normalize({ n: a.n, s: a.s - k })
}

export function cmp(a: Dec, b: Dec): number {
  const [x, y] = align(a, b)
  return x < y ? -1 : x > y ? 1 : 0
}

export const neg = (a: Dec): Dec => ({ n: -a.n, s: a.s })
export const abs = (a: Dec): Dec => (a.n < 0n ? neg(a) : a)

/** a / b rounded half-to-even to `scale` decimals. Null when b is zero. */
export function div(a: Dec, b: Dec, scale: number): Dec | null {
  if (b.n === 0n) return null
  // a/b = (a.n / 10^a.s) / (b.n / 10^b.s) = a.n * 10^(b.s - a.s) / b.n; scale up by 10^scale.
  let num = a.n * pow10(scale + b.s)
  let den = b.n * pow10(a.s)
  if (den < 0n) {
    num = -num
    den = -den
  }
  let q = num / den
  const r = num % den
  const twice = (r < 0n ? -r : r) * 2n
  if (twice > den || (twice === den && q % 2n !== 0n)) q += num < 0n ? -1n : 1n
  return normalize({ n: q, s: scale })
}

/** Rounds half-to-even to `scale` decimals (never adds precision). */
export function round(a: Dec, scale: number): Dec {
  if (a.s <= scale) return a
  return div(a, fromInt(1), scale) ?? a
}

export function sum(values: Dec[]): Dec {
  let total = ZERO
  for (const v of values) total = add(total, v)
  return total
}

export function min(values: Dec[]): Dec | null {
  return values.reduce<Dec | null>((m, v) => (m === null || cmp(v, m) < 0 ? v : m), null)
}

export function max(values: Dec[]): Dec | null {
  return values.reduce<Dec | null>((m, v) => (m === null || cmp(v, m) > 0 ? v : m), null)
}

/** The mean, rounded half-to-even to `scale` decimals. */
export function mean(values: Dec[], scale: number): Dec | null {
  if (values.length === 0) return null
  return div(sum(values), fromInt(values.length), scale)
}

/** The median; an even count averages the two middle values exactly (one extra decimal at most). */
export function median(values: Dec[]): Dec | null {
  if (values.length === 0) return null
  const sorted = [...values].sort(cmp)
  const mid = Math.floor(sorted.length / 2)
  if (sorted.length % 2 === 1) return sorted[mid]
  const pair = add(sorted[mid - 1], sorted[mid])
  return div(pair, fromInt(2), Math.max(pair.s, 0) + 1)
}

/** Canonical string with every stored decimal: "-1234.5". */
export function toString(a: Dec): string {
  const neg = a.n < 0n
  let digits = (neg ? -a.n : a.n).toString()
  if (a.s > 0) {
    digits = digits.padStart(a.s + 1, '0')
    digits = `${digits.slice(0, -a.s)}.${digits.slice(-a.s)}`
  }
  return neg ? `-${digits}` : digits
}

/** For drawing only: the float nearest to the exact value. */
export const toNumber = (a: Dec): number => Number(toString(a))
