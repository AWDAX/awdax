"""Writes tests/fixtures/ask_math.json: one 30-row table and the exact answers to questions about it.

The expected answers are computed here from exact values written beside each cell, NOT by the code under test, so both the
Python engine (query_engine.py) and the browser engine (Frontend/src/analytics/aggregate.ts) are checked against the same
independent truth. Regenerate with `python tests/fixtures/make_ask_math.py` after changing the data.
"""

from __future__ import annotations

import json
from decimal import ROUND_HALF_EVEN, Decimal as D
from pathlib import Path

CATS = ["Cafe", "Clinic", "Salon", "Gym", "Bakery"]
# (price text, exact price in rupees or None, "ranged": the cell is a range counted at its low end)
PRICES = [
    ("₹12.5 Lakh", D(1250000)), ("₹8,50,000", D(850000)), ("₹1.2 Crore", D(12000000)), ("₹11 – ₹15 Lakh", D(1100000)), ("N/A", None),
    ("₹95,000", D(95000)), ("₹22 Lakh", D(2200000)), ("₹7.25 Lakh", D(725000)), ("Contact us", None), ("₹3,40,000", D(340000)),
    ("₹18.9 Lakh", D(1890000)), ("₹2.5 Crore", D(25000000)), ("₹6 Lakh", D(600000)), ("₹15,00,000", D(1500000)), ("₹9.99 Lakh", D(999000)),
    ("₹45,000", D(45000)), ("₹30 Lakh", D(3000000)), ("₹4.75 Lakh", D(475000)), ("₹13.2 Lakh", D(1320000)), ("—", None),
    ("₹5.5 Lakh", D(550000)), ("₹19,99,999", D(1999999)), ("₹1 Crore", D(10000000)), ("₹8 Lakh", D(800000)), ("₹16.4 Lakh", D(1640000)),
    ("₹2,75,000", D(275000)), ("₹21 Lakh", D(2100000)), ("₹10.1 Lakh", D(1010000)), ("₹14 Lakh", D(1400000)), ("₹3.3 Lakh", D(330000)),
]
RATINGS = ["4.5", "4.1", "3.9", "4.8", "N/A", "4.2", "4.5", "3.5", "4.0", "4.7", "4.3", "3.8", "4.6", "4.4", "4.1", "3.2", "4.9", "4.0", "4.5", "4.2",
           "3.7", "4.6", "4.3", "4.8", "4.1", "3.9", "4.4", "4.5", "4.2", "4.0"]
REVIEWS = ["1,204", "87", "12,345", "450", "33", "2,100", "876", "15", "5,432", "301", "99", "1,010", "64", "7,777", "222", "8", "3,500", "410", "56", "980",
           "1,500", "2,222", "130", "76", "640", "18", "4,040", "905", "260", "3,141"]
DISCOUNTS = ["12%", "7.5%", "0%", "15%", "10%", "5%", "20%", "7.5%", "12%", "8%", "3%", "25%", "9%", "11%", "6.5%", "4%", "18%", "10%", "13%", "2%",
             "14%", "9.5%", "1%", "16%", "7%", "12%", "5.5%", "8%", "10%", "22%"]
RANGES = [str(n) + " km" for n in (450, 380, 520, 410, 300, 275, 600, 330, 290, 480, 550, 640, 360, 425, 500, 310, 700, 390, 445, 405, 335, 460, 590, 375, 430, 285, 620, 395, 415, 345)]

columns = ["name", "category", "price", "range_km", "rating", "reviews", "discount", "website", "phone"]
rows = []
for i in range(30):
    rows.append([
        f"Place {i + 1:02d}", CATS[i % 5], PRICES[i][0], RANGES[i], RATINGS[i], REVIEWS[i], DISCOUNTS[i],
        f"https://site{i % 4}.example/p{i}" if i % 3 else "", f"098{i:02d} {1000 + i * 7}",
    ])

price = [p[1] for p in PRICES]
rating = [None if r == "N/A" else D(r) for r in RATINGS]
reviews = [D(r.replace(",", "")) for r in REVIEWS]
discount = [D(d.rstrip("%")) for d in DISCOUNTS]
rng = [D(r.split()[0]) for r in RANGES]
cats = [r[1] for r in rows]
names = [r[0] for r in rows]
has_site = [bool(r[7]) for r in rows]


def q2(x: D, places: int) -> D:
    return x.quantize(D(1).scaleb(-places), rounding=ROUND_HALF_EVEN)


def scale_of(texts: list[str]) -> int:
    return max((len(t.split(".")[1]) if "." in t else 0) for t in texts)


def avg(values: list[D], scale: int) -> D:
    return q2(sum(values) / D(len(values)), scale + 2)


def median(values: list[D]) -> D:
    s = sorted(values)
    m = len(s) // 2
    if len(s) % 2:
        return s[m]
    pair = s[m - 1] + s[m]
    places = max(-pair.as_tuple().exponent, 0) + 1
    return q2(pair / D(2), places)


def num(x: D | None) -> int | float | None:
    if x is None:
        return None
    return int(x) if x == x.to_integral_value() else float(x)


def grouped(keys: list[str], values: list[D | None], fn, *, order: str = "desc", limit: int | None = None, need_value: bool = True):
    groups: dict[str, list] = {}
    for k, v in zip(keys, values):
        if need_value and v is None:
            continue
        groups.setdefault(k, []).append(v)
    out = [(k, fn(vs), len(vs)) for k, vs in groups.items()]
    out.sort(key=lambda t: t[0].lower())
    out.sort(key=lambda t: t[1], reverse=(order == "desc"))
    return out[:limit] if limit else out


price_scale, rating_scale, discount_scale = 0, 1, 1
cases = []


def add(question, plan, rows_out, overall, used, matched=None):
    cases.append({"question": question, "plan": plan, "expect": {"rows": rows_out, "overall": num(overall) if isinstance(overall, D) else overall, "used": used, "matched": matched if matched is not None else used}})


def row(label, value, count):
    return [label, num(value), count]


# totals over everything
add("how many rows", {"agg": "count"}, [row("All rows", D(30), 30)], D(30), 30)
rated = [r for r in rating if r is not None]
add("average rating", {"agg": "avg", "measure": "rating"}, [row("All rows", avg(rated, rating_scale), len(rated))], avg(rated, rating_scale), len(rated), 30)
add("total reviews", {"agg": "sum", "measure": "reviews"}, [row("All rows", sum(reviews), 30)], sum(reviews), 30)
priced = [p for p in price if p is not None]
add("highest price", {"agg": "max", "measure": "price"}, [row("All rows", max(priced), len(priced))], max(priced), len(priced), 30)
add("lowest price", {"agg": "min", "measure": "price"}, [row("All rows", min(priced), len(priced))], min(priced), len(priced), 30)
add("total price", {"agg": "sum", "measure": "price"}, [row("All rows", sum(priced), len(priced))], sum(priced), len(priced), 30)
add("average price", {"agg": "avg", "measure": "price"}, [row("All rows", avg(priced, price_scale), len(priced))], avg(priced, price_scale), len(priced), 30)
add("median rating", {"agg": "median", "measure": "rating"}, [row("All rows", median(rated), len(rated))], median(rated), len(rated), 30)
add("median reviews", {"agg": "median", "measure": "reviews"}, [row("All rows", median(reviews), 30)], median(reviews), 30)
add("average discount", {"agg": "avg", "measure": "discount"}, [row("All rows", avg(discount, discount_scale), 30)], avg(discount, discount_scale), 30)
add("highest range", {"agg": "max", "measure": "range_km"}, [row("All rows", max(rng), 30)], max(rng), 30)
add("different categories", {"agg": "distinct", "measure": "category"}, [row("All rows", D(5), 30)], D(5), 30)

# grouped
by_cat_price = grouped(cats, price, lambda vs: avg(vs, price_scale))
add("average price by category", {"agg": "avg", "measure": "price", "groupBy": "category", "sort": "value-desc"}, [row(k, v, c) for k, v, c in by_cat_price], avg(priced, price_scale), len(priced), 30)
by_cat_count = grouped(cats, [D(1)] * 30, lambda vs: D(len(vs)), need_value=False)
add("count by category", {"agg": "count", "groupBy": "category", "sort": "value-desc"}, [row(k, v, c) for k, v, c in by_cat_count], D(30), 30)
by_cat_reviews = grouped(cats, reviews, lambda vs: sum(vs), limit=3)
add("total reviews by category, top 3", {"agg": "sum", "measure": "reviews", "groupBy": "category", "sort": "value-desc", "limit": 3}, [row(k, v, c) for k, v, c in by_cat_reviews], sum(reviews), 30)
by_cat_rating = grouped(cats, rating, lambda vs: avg(vs, rating_scale), order="asc")
add("average rating by category, lowest first", {"agg": "avg", "measure": "rating", "groupBy": "category", "sort": "value-asc"}, [row(k, v, c) for k, v, c in by_cat_rating], avg(rated, rating_scale), len(rated), 30)
top_reviews = grouped(names, reviews, lambda vs: max(vs), limit=3)
add("top 3 by reviews", {"agg": "max", "measure": "reviews", "groupBy": "name", "sort": "value-desc", "limit": 3}, [row(k, v, c) for k, v, c in top_reviews], max(reviews), 30)
bottom_rating = grouped(names, rating, lambda vs: min(vs), order="asc", limit=2)
add("bottom 2 by rating", {"agg": "min", "measure": "rating", "groupBy": "name", "sort": "value-asc", "limit": 2}, [row(k, v, c) for k, v, c in bottom_rating], min(rated), len(rated), 30)
by_cat_median = grouped(cats, reviews, lambda vs: median(vs))
add("median reviews by category", {"agg": "median", "measure": "reviews", "groupBy": "category", "sort": "value-desc"}, [row(k, v, c) for k, v, c in by_cat_median], median(reviews), 30)

# filters
idx_good = [i for i in range(30) if rating[i] is not None and rating[i] >= D("4.5")]
add("places rated 4.5 or more", {"agg": "count", "filters": [{"column": "rating", "op": "gte", "values": ["4.5"]}]}, [row("All rows", D(len(idx_good)), len(idx_good))], D(len(idx_good)), len(idx_good))
idx_cg = [i for i in range(30) if cats[i] in ("Cafe", "Gym")]
add("reviews of cafes and gyms", {"agg": "sum", "measure": "reviews", "filters": [{"column": "category", "op": "in", "values": ["Cafe", "gym"]}]}, [row("All rows", sum(reviews[i] for i in idx_cg), len(idx_cg))], sum(reviews[i] for i in idx_cg), len(idx_cg), len(idx_cg))
idx_site = [i for i in range(30) if has_site[i]]
add("places with a website", {"agg": "count", "filters": [{"column": "website", "op": "present", "values": []}]}, [row("All rows", D(len(idx_site)), len(idx_site))], D(len(idx_site)), len(idx_site))
idx_mid = [i for i in range(30) if price[i] is not None and D(500000) <= price[i] <= D(2000000)]
add("priced between 5 and 20 lakh", {"agg": "count", "filters": [{"column": "price", "op": "between", "values": ["5 lakh", "20 lakh"]}]}, [row("All rows", D(len(idx_mid)), len(idx_mid))], D(len(idx_mid)), len(idx_mid))
idx_cheap = [i for i in range(30) if price[i] is not None and price[i] <= D(500000)]
add("priced up to 5 lakh, average rating", {"agg": "avg", "measure": "rating", "filters": [{"column": "price", "op": "lte", "values": ["5 lakh"]}]},
    [row("All rows", avg([rating[i] for i in idx_cheap if rating[i] is not None], rating_scale), len([i for i in idx_cheap if rating[i] is not None]))],
    avg([rating[i] for i in idx_cheap if rating[i] is not None], rating_scale), len([i for i in idx_cheap if rating[i] is not None]), len(idx_cheap))
idx_p1 = [i for i in range(30) if "place 1" in names[i].lower()]
add("names containing Place 1", {"agg": "count", "filters": [{"column": "name", "op": "contains", "values": ["Place 1"]}]}, [row("All rows", D(len(idx_p1)), len(idx_p1))], D(len(idx_p1)), len(idx_p1))
idx_search = [i for i in range(30) if any("site2" in c.lower() for c in rows[i])]
add("any cell mentions site2", {"agg": "count", "filters": [{"op": "search", "values": ["site2"]}]}, [row("All rows", D(len(idx_search)), len(idx_search))], D(len(idx_search)), len(idx_search))
idx_not = [i for i in range(30) if cats[i] != "Salon"]
add("everything except salons", {"agg": "count", "filters": [{"column": "category", "op": "notIn", "values": ["Salon"]}]}, [row("All rows", D(len(idx_not)), len(idx_not))], D(len(idx_not)), len(idx_not))

fixture = {
    "note": "Generated by make_ask_math.py. Expected answers are computed there from exact values, not by the engines.",
    "columns": columns,
    "rows": rows,
    "ranged_price_rows": [i for i, p in enumerate(PRICES) if "–" in p[0]],
    "unreadable_price_cells": [PRICES[i][0] for i in range(30) if PRICES[i][1] is None],
    "cases": cases,
}
out = Path(__file__).with_name("ask_math.json")
out.write_text(json.dumps(fixture, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"wrote {out} with {len(cases)} cases")
