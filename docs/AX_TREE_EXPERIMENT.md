# Accessibility tree vs the current page digest

Run on 2026-10-07 with Gemini `gemini-3.5-flash`, default settings, JSON output. The measurement scripts were one-off and are not kept; the method below is
enough to repeat it, and the result is now what `ax_reader.py` implements.

## Question

Does giving the model the browser's accessibility tree (what Chrome builds for screen readers) instead of the page's HTML digest cost fewer
tokens and return more correct rows?

## Method

Four pages, each loaded once in headless Chrome after the page stopped changing. The same prompt, schema and model for every method; each
method run twice per page (32 model calls). Context capped at 180,000 characters for every method, as the pipeline does.

| Method | What the model is given |
|---|---|
| A Digest (current) | The pipeline's own `build_gemini_page_context` on the rendered HTML: JSON-LD, app data, the biggest tables as rows, visible text. |
| B AX tree raw | `Accessibility.getFullAXTree`, printed as an indented tree (role "name"), ignored and generic nodes folded away. |
| C AX tree compact | The same tree with each table row on one line (`row: a \| b \| c`), list items and cards folded to one line each. |
| D Visible text only | `document.body.innerText`. |

Ground truth was built outside the model: regexes on the page markup (books, countries), the site's own JSON API (sansad), the HTML table parser
(Wikipedia). A row counts as correct only when its key and every field match (numbers by value, dates by date, text by normalised text).

| Page | Layout | Truth rows |
|---|---|---|
| books.toscrape.com | cards, no table | 20 |
| scrapethissite.com/pages/simple | 250 countries as divs | 250 |
| sansad.in/ls/debates/digitized | React table, button paging | 10 (page 1) |
| Wikipedia, Indian Institutes of Technology | real HTML table | 23 |

## Results (mean of two runs; input tokens as counted by Gemini)

| Page | Method | Input tokens | Correct rows | Seconds |
|---|---|---:|---:|---:|
| Books (cards) | A Digest | 884 | **10 / 20** | 6.5 |
| | B AX raw | 4,016 | 20 / 20 | 9.2 |
| | C AX compact | 2,071 | 20 / 20 | 7.5 |
| | D Visible text | 1,390 | **10 / 20** | 5.8 |
| Countries (divs) | A Digest | 7,931 | 250 / 250 | 64.1 |
| | B AX raw | 16,503 | 250 / 250 | 95.4 |
| | C AX compact | 13,043 | 250 / 250 | 68.3 |
| | D Visible text | 10,289 | 250 / 250 | 66.8 |
| Sansad LS (button paging) | A Digest | **59,494** | 10 / 10 | 8.9 |
| | B AX raw | 2,733 | 10 / 10 | 6.2 |
| | C AX compact | **2,027** | 10 / 10 | 5.6 |
| | D Visible text | 1,814 | 10 / 10 | 5.9 |
| Wikipedia IITs (real table) | A Digest | 11,982 | 23 / 23 | 11.6 |
| | B AX raw | 39,315 | 23 / 23 | 10.9 |
| | C AX compact | 29,639 | 23 / 23 | 10.8 |
| | D Visible text | 21,501 | 23 / 23 | 12.1 |

Across the four pages: input tokens A 80,291, B 62,567, **C 46,780**, D 34,994. Mean share of rows exactly right: A 0.875, **B 1.000, C 1.000**,
D 0.875. No method invented rows or got a number wrong; every miss was a title that was not the full title.

## Button paging (sansad, the AX tree only)

The tree lists the pager as buttons (`Go to next page`, `Go to page 2` ...). The digest has no mention of them (checked: it contains neither
"go to next page" nor "go to page 2"). Using the tree, the next-page button was found and clicked through Chrome, the table changed, and the
model read the new page. Rows correct against the site's API:

| Page | Input tokens | Correct rows |
|---|---:|---:|
| 1 | 2,022 | 10 / 10 |
| 2 (clicked) | 2,085 | 10 / 10 |
| 3 (clicked) | 2,155 | 10 / 10 |

## What it shows

1. **Accuracy.** On the card layout, the digest and the visible text both returned only 10 of 20 titles: the page shows long titles cut off with "..." (`A Light
   in the ...`) and keeps the full title in an attribute. The tree uses the attribute as the link's name, so it had all 20. Anything that reads only the
   visible words loses information that the browser knows.
2. **Tokens.** The digest of a JavaScript page can be enormous: sansad cost 59,494 tokens (the app's boot data fills the cap) against 2,027 for the compact tree
   (29 times fewer) with the same correct answer. The other way round on a content-heavy page: for Wikipedia the digest (which keeps only the biggest tables) was
   smaller than the whole-page tree (12k against 30k tokens).
3. **Layout does not matter.** Divs, cards and real tables were all read exactly by the tree.
4. **Clicking.** The tree gives named, clickable controls; the digest gives none. That is what lets a run go past page 1 on a site with no data feed.
5. **Time.** The tree needs a browser (about 6-7 s to load and settle here). The model call time was about the same for all methods; the long
   countries answer (13,000 output tokens) dominated its runtime.

## Limits of this test

- Four pages, two runs each: indicative, not statistical. The model's reasoning ("thinking") tokens varied from run to run, so only input tokens and correct rows
  are compared.
- The compact format is my own design; a different serialisation would move the token numbers. The full-page tree is wasteful on text-heavy pages and would
  be better restricted to the main region or the table.
- Not tested: iframes, shadow DOM, sites with poor accessibility markup (unlabelled clickable divs), pages that only render the rows on screen, infinite scroll,
  sites that block headless browsers.
- A data feed (sansad's JSON API, 746,595 rows on the other chamber) is still better than any page reading: exact, complete, and no model call per page.

## Recommendation

Use the compact accessibility tree instead of the HTML digest for pages that are opened in the browser anyway, restricted to the main region. Keep plain-fetch +
digest for simple static pages (no browser), and keep data feeds and data files first. Add a click-through step driven by the tree for pages that have a pager but no feed.
