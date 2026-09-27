AWDAX Autonomous Web Data Acquisition & eXtraction

bot finds legit good source of data (using google dorking or something)

bot goes into website (headless brwser) tells up what it sees

if data can be fetched by simple http request then its good if not then bot will use vision to navigate in website to get to the data and make a set of rules using preexisting code if code does not pre exist then it'll ask coding agent to cook something based on requirements then it'll scrape all the necessary requirements

the agent will decide what columns will be needed

then it'll fetch all the data in for of tables (multiple tables if needed)

based on this data it'll make a dashboard like power BI

**Live mode (on by default):** after you send a goal, the server keeps refreshing on an interval (`LIVE_REFRESH_INTERVAL_SECONDS`, default 5 min). The **Live** bar shows the current phase (discovery / extract / merge) and source; the **Live dataset** panel updates via SSE. Toggle **Live** off to pause. New rows are merged in; changed prices/fields overwrite older values per source+model key.

user will be able to create multiple such instances if needed

```
                     USER
                       │
                       ▼
            ┌─────────────────────┐
            │   NATURAL LANGUAGE  │
            │ "Track Indian EV    │
            │  sales every month" │
            └──────────┬──────────┘
                       │
                       ▼
             ┌───────────────────┐
             │   PLANNER AGENT   │
             │                   │
             │ What data?        │
             │ What columns?     │
             │ What frequency?   │
             │ What sources?     │
             └─────────┬─────────┘
                       │
                       ▼
            ┌─────────────────────┐
            │   SOURCE DISCOVERY  │
            │                     │
            │ Search / Dorking    │
            │ Source validation   │
            │ Source ranking      │
            └──────────┬──────────┘
                       │
                       ▼
            ┌─────────────────────┐
            │  SOURCE INSPECTOR   │
            │                     │
            │ HTTP/API?           │
            │ HTML?               │
            │ JS rendered?        │
            │ PDF?                │
            │ Login?              │
            └──────────┬──────────┘
                       │
          ┌────────────┼─────────────┐
          ▼            ▼             ▼
      HTTP/API      Browser       Document
          │            │             │
          │       ┌────┴─────┐       │
          │       │ Vision   │       │
          │       │ Agent    │       │
          │       └────┬─────┘       │
          │            │             │
          └────────────┼─────────────┘
                       ▼
            ┌─────────────────────┐
            │ EXTRACTION ENGINE   │
            │                     │
            │ Existing scraper?   │
            │       ↓             │
            │ Use it              │
            │                     │
            │ No?                 │
            │       ↓             │
            │ Coding Agent        │
            │       ↓             │
            │ Generate extractor  │
            └──────────┬──────────┘
                       ▼
            ┌─────────────────────┐
            │   DATA VALIDATOR    │
            │                     │
            │ Schema              │
            │ Types               │
            │ Duplicates          │
            │ Missing values      │
            │ Anomalies           │
            │ Source consistency  │
            └──────────┬──────────┘
                       ▼
             ┌──────────────────┐
             │  DATA WAREHOUSE  │
             └────────┬─────────┘
                      │
         ┌────────────┴────────────┐
         ▼                         ▼
  LIVE DASHBOARD              SCHEDULER
         │                         │
         │                    every X hours
         │                         │
         │                         ▼
         │                  Fetch latest data
         │                         │
         └────────────◄────────────┘
```