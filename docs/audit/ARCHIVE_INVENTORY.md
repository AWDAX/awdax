# Archive inventory: `##Documentation_Fixes.zip`

44 entries: 5 Markdown reports, 33 images (one byte-identical duplicate) and 6 folders. The raw files are kept git-excluded in `.agent/inputs/##Documentation_Fixes/`.
All 33 images and all 5 reports were read for this audit. Claim IDs refer to CLAIM_VALIDATION.md.

## Reports

| File | Says | Main claims |
|---|---|---|
| `3_MD_FILES_HARSHIT/1_Code_Changes_Detail.md` | Changes over 48 h by branch | C1, C2, C15, C18, C19 |
| `3_MD_FILES_HARSHIT/2_Caught_Issues_Detail.md` | Root causes: SQLite deadlock, title race, normalisation, donut | C6, C7, C11, C15, C18 |
| `3_MD_FILES_HARSHIT/3_Current_Site_Update.md` | `awdax.synapical.com` 524 outage; merge `frontend` to fix | C6–C10, C21 |
| `Z+ More/changes_past_2_days.md` | Commit list split into `frontend` and `main` | Branch facts (mostly already merged) |
| `Z+ More/issues_and_fixes_report.md` | Same outage story; merge-conflict forecast | C6–C10 |

## `ISSUE/` screenshots (20 files)

| File | Shows | Claim |
|---|---|---|
| `NORMALISATION_NOT_DONE_ISSUE.webp` | Total ₹24,81,65,000 and average ₹1,18,17,380.95; 21 rows used, 47 left out | C16, C17 |
| `Screenshot 2026-10-02 040318.png` | A teammate sees an EV chat they never made ("this is a data leak issue") | C4 |
| `Screenshot_2026-10-01_123347.webp` | New account sees 2 untitled chats; an earlier assistant answers "not a data leak" | C4 (refuted) |
| `Screenshot_2026-10-01_123405.webp`, `…123405 (1).webp` | Same answer, conclusion and options (byte-identical duplicates) | C4 |
| `Screenshot_2026-10-01_124249.webp`, `…124303.webp` | Assistant admits the backend decodes JWTs without verification | C2 |
| `Screenshot_2026-10-01_171254.webp` | Untitled chat for a Rajya Sabha/Lok Sabha request; run complete; 74 rows | C19 (historical) |
| `UNTITLED CHAT ISSUE.webp` | Three "Untitled chat" entries, eGazette source, 74 rows | C19 (historical) |
| `Screenshot_2026-10-01_215115.webp`–`215151.webp` (5) | Normalisation analysis: ranges rejected, luxury cars skew the average, proposed midpoint and trimmed mean | C15, C16, C17 |
| `Screenshot_2026-10-01_233215.webp`, `…233244.webp` | GitHub commit list for `f59f7a9`, `e52a920`, `93f6dd5`, `124caa8`, `d5e6f7b`, `b593021` | Branch facts |
| `Screenshot_2026-10-01_234052.webp`–`234111.webp` (4) | Backend deadlock analysis: where, why, symptoms, plan (WAL, close before I/O, flags before start, SSE throttle) | C6, C7, C12–C14 |

## `RESOLVED/` screenshots (13 files)

| File | Shows | Claim |
|---|---|---|
| `PROXY ISSUE.webp` | "Will the proxy issue recur? No"; says `main` deploys to `awdax.synapical.com` | C3, C10 |
| `Screenshot 2026-10-02 035718.png` | UI stabilisation summary (BellToggle, FuseButton, ExportDialog, fullscreen) | Already on `main` |
| `Screenshot 2026-10-02 035732.png` | JWT verification, proxy forwarding, auto-naming, "39/39 tests" | C2, C3, C19, C20 |
| `Screenshot 2026-10-02 040130.png`, `…040138.png` | `233fb40` summary: noise cleaning, range midpoints, `trimmedMean`, tests | C15, C16 |
| `Screenshot_2026-10-01_124323.webp` | "Rigorously tested", anonymous fallback | C5 |
| `Screenshot_2026-10-01_124922.webp` | PyJWT added; "immune to that theoretical vulnerability" | C2 (refuted) |
| `Screenshot_2026-10-01_125012.webp` | "Nothing will break"; old chats stay in `anonymous`; fallback if the secret is missing | C2, C5 |
| `Screenshot_2026-10-01_133223.webp` | Delivered summary: isolation, JWT, renaming | C1, C2 |
| `Screenshot_2026-10-01_134551.webp` | Proxy was stripping `Authorization`; fix pushed to `main` | C3 |
| `Screenshot_2026-10-02_005356.webp`–`005407.webp` (3) | "Deadlock completely resolved"; "17/17 tests" | C7, C12, C13, C20 |

## Gaps in the archive

- **No screenshot of the 524 error or of HTML in the sidebar**, though both reports describe one ("as shown in your recent screenshots").
- No production logs, no deployment configuration, no database file, no `.env` (correctly).
- The 68-row EV dataset behind the normalisation screenshots is absent, so C17 cannot be reproduced.
- The `RESOLVED/` folder records what an assistant **said** was fixed. It does not certify that anything is fixed on `main`.
