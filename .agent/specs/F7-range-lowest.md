# F7: a range counts as its lowest value (rework of `233fb40`)

Branch `feat/range-lowest-value`, cut from `main`. Owner decision (2 October 2026): a range such as "₹11.45 – ₹26.95 Lakh" counts
as its **lowest** value everywhere (totals, averages, min, max). No midpoint and no trimmed mean. The table keeps showing the
original text.

`233fb40` on `origin/frontend` (read it with `git show 233fb40`) took the midpoint, swapped descending ends, and accepted bare digit
ranges ("2024-25", "98765-43210"). **Do not cherry-pick it.** Reuse only its ideas: scale written once applies to both ends, and a
trailing footnote star is not part of the number.

## Files you may edit

- `Frontend/src/analytics/parse.ts`
- `Frontend/src/analytics/core.test.ts`
- `Frontend/src/analytics/profile.ts`
- `Frontend/src/analytics/aggregate.ts`
- `Frontend/src/app/dashboard/PrecisionNote.tsx`
- `Frontend/src/app/dashboard/DataGrid.tsx`
- `Frontend/src/app/graphs/GraphsPanel.tsx`
- `Frontend/src/app/export/ExportDialog.tsx`

## 1. `parse.ts`

`ParsedNumber` gets one field:
```ts
/** The cell was a range ("₹11.45 – ₹26.95 Lakh"): `value` is its low end. */
range?: { low: Dec; high: Dec }
```

Split today's `parseNumber` string path into a private `readOne(s)` (everything after the missing check: approx prefix, brackets,
currency, sign, percent, digits, scale word, suffix) **without** the range-refusal line. `parseNumber` for strings becomes:

1. `s = input.trim()`, then strip a trailing footnote marker: `s.replace(/\s*[*†‡]+$/, '')`, so "₹7.99 Lakh*" reads as "₹7.99 Lakh".
   Only trailing markers. Not `#`, not in the middle.
2. `isMissingText(s)` → missing (as today).
3. `readRange(s)`: if it returns a result, return it.
4. Otherwise keep today's refusal exactly: `/\b(to|and)\b|\d\s*[-–—]\s*\d/i` → `{ ok: false, missing: false, reason: 'a range, not one number' }`.
5. Otherwise `return readOne(s)`.

The number path (`typeof input === 'number'`) and `null`/`undefined` handling are unchanged.

`readRange(s)` (private) returns a `NumberRead` or `null`:
- `null` if `s` starts with `-`, `−`, `+` or `(`.
- Split once at the first separator: `/^(.+?)\s*(?:[-–—]|\bto\b)\s*(.+)$/i`. Both halves must pass `readOne`, otherwise `null`.
- The two ends must describe one quantity, otherwise `null`:
  - two different currencies
  - two different suffixes
  - a percent on either end together with a currency or a suffix on either end
- **Bare digit ranges stay refused**: if neither end has a currency, a scale word, a suffix or a percent, return `null`.
  "10-20", "2019–2024", "2024-25" and "98765-43210" are years, pages and phone numbers as often as quantities.
- A suffix that contains a digit is not a unit: return `null`. `readOne` accepts short phrases such as "km/h in 9.5 s"
  as a suffix, so "0-100 km/h in 9.5 s" would otherwise read as the range 0–100.
- A scale word written on one end only applies to both ("Rs. 24.99 - 34.49 Lakh"). Shift the other end by that word's power of ten.
  Look the power up from the existing `SCALES` table by its name (third tuple element). Don't add a second table. When both ends
  have scale words ("₹95 Lakh - ₹1.2 Cr"), use each end as read.
- Written high to low (after scaling): return `null`. Never swap the ends.
- Success: `{ ok: true, num: { value: low, range: { low, high }, currency, suffix, percent, scaleWord, approx } }`, where each field
  is the first end's value if set, else the second's. `percent` and `approx` are only set when true, like today.

Update the module comment at the top in one line: ranges of one measured quantity count as their lowest value.

## 2. Tests in `core.test.ts`, written first

Keep every existing assertion (including `'10-20'` in the refused list). Add:

- `numbers: a range of one quantity counts as its lowest value`:
  `'Rs. 24.99 - 34.49 Lakh'` → value 2499000, `range.high` 3449000, currency INR.
  `'₹1.95 - ₹2.65 Cr*'` → 19500000, high 26500000.
  `'₹11.45 – ₹26.95 Lakh*'` (en dash) → 1145000.
  `'10 to 15 Lakh'` → 1000000, high 1500000.
  `'450 - 500 km'` → 450, suffix `km`.
  `'10-15%'` → 10, percent true.
  `'₹95 Lakh - ₹1.2 Cr'` → 9500000, high 12000000.
  `'~10-12 lakh'` → 1000000, approx true.
- `numbers: look-alikes of ranges stay refused` (each `!ok && !missing`): `'10-20'`, `'2019–2024'`, `'2024-25'`, `'98765-43210'`,
  `'₹20 - 10 Lakh'`, `'$10 - ₹20'`, `'10 km - 20 kWh'`, `'Up to 500 km'`, `'500 and above'`, `'0-100 km/h in 9.5 s'`.
- `numbers: a trailing footnote star is ignored`: `'₹7.99 Lakh*'` → 799000; `'N/A*'` → missing; `'₹ 5,000/-'` still 5000.
- A profile and query test: a column `['₹7.99 Lakh*', '₹11.45 – ₹26.95 Lakh*', '₹9 Lakh']` with a category column beside it.
  It profiles as `money`, the numbers are 799000 / 1145000 / 900000, `ranged` is `[false, true, false]`, nothing is excluded.
  A `runQuery` average or sum over it reports `ranged === 1`. Build the table the way the existing profile tests in this file do.

## 3. Surface it where the app already explains what it counted

Read this decision honestly: the user must be able to see that a range was read as its low end.

- `profile.ts`: `ColumnProfile` gets
  `/** Numeric kinds: true for each row whose cell was a range, counted at its lowest value. Absent when no cell was. */ ranged?: boolean[]`.
  In the numeric branch, after `numbers[x.row] = p.value`, mark the row when `p.range` is set. Return `ranged` only if any row was marked.
- `aggregate.ts`: `QueryResult` gets `/** Used rows whose value was a range, counted at its lowest value. */ ranged: number`.
  In `runQuery`: `needsValue && measure?.ranged ? usedRows.filter((r) => measure.ranged![r]).length : 0`.
- `PrecisionNote.tsx`: append to `text`, when `result.ranged > 0`: `` · ${plural(result.ranged, 'range')} counted at the lowest value ``.
- `GraphsPanel.tsx`: in the "rows used" line, the same clause after the invalid-values clause, using `plural` from `analytics/format.ts`.
- `DataGrid.tsx` `Cell`: when `col.ranged?.[row]`, the title becomes `` `Read as ${formatFor(col, parsed)}, the lowest value of the range` ``.
- `ExportDialog.tsx`: in the existing note paragraph under the preview, when any column of `profile` has `ranged`, add one
  sentence: `Ranges are exported as their lowest value; tick “Values exactly as scraped” to keep the text.`

No other UI changes. Keep the existing markup and classes; only text is added.

## Must stay true

- Every value that parses today parses to the same result (the existing tests prove it).
- Nothing that is refused today becomes a number, except (a) a range of one measured quantity and (b) a value whose only
  problem was a trailing `*`, `†` or `‡`.
- A missing value is never 0.
