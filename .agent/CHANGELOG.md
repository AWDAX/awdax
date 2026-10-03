# CHANGELOG — AWDAX

> **Responsibility:** what actually shipped.
> Append-only, one entry per completed task. Written when a task reaches DONE,
> which can only happen once its evidence passes.
>
> `PLAN.md` is intent. This is outcome. The difference between them over time
> is the honest record of how the project went.

---

## Q1 — Backend: delete verified dead functions and unused imports

_2026-10-03 05:24_ · code:PASS · code `00aa1c520ddb`

## Q2 — Frontend: delete CallChip and unused exports

_2026-10-03 05:30_ · code:PASS ui:PASS · code `3697a3a54295`

## Q3 — Frontend: remove the switched-off Ask database page (chat's Ask box stays)

_2026-10-03 05:33_ · code:PASS ui:PASS · code `faed386b03da`

## Q4 — Backend: retire the legacy pre-React API and the old root page

_2026-10-03 05:39_ · code:PASS ui:PASS · code `931f7b734a43`

## Q5 — Backend: one shared Selenium import, dependency list trimmed

_2026-10-03 05:40_ · code:PASS · code `b7e5b01c9bb2`

## Q6 — Backend: scrape sources in parallel, database writes serialized

_2026-10-03 06:02_ · code:PASS · code `51b508456861`

## Q7 — Frontend: no Untitled chat flash while a chat loads

_2026-10-03 06:05_ · code:PASS ui:PASS · code `c3e3ce341a4f`

## Q8 — Frontend: measure bundles, lazy-load what slows first paint

_2026-10-03 06:10_ · code:PASS ui:PASS · code `3a497929fa35`

## Q9 — Backend: split scraper.py and RegulatoryFeed.py into smaller modules, no behaviour change

_2026-10-03 06:14_ · code:PASS · code `1b48e6b74ffb`

## Q12 — Apply the re-audit cuts: dead html_extract extractors + dev CLIs + unused service methods, write-only LiveBridge map, duplicate helpers, unused frontend exports

_2026-10-03 09:45_ · code:PASS ui:PASS · code `4065e34c7ae6`

## Q13 — Backend: import PyMuPDF by its current name so a future release can't silently drop PDF text extraction

_2026-10-03 09:47_ · code:PASS · code `e27eb7f8e577`
