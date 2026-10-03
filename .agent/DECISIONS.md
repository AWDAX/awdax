# DECISIONS — AWDAX

> **Responsibility:** why things are the way they are.
> Append-only. Each entry records a choice and the reasoning behind it, so a
> future session does not relitigate a settled question or silently reverse it.
>
> Written by `loop note "<what>" --decision --why "<reasoning>"`.

Record a decision when:

- two reasonable implementations were possible and one was chosen
- a constraint was discovered that changes the plan
- something was deliberately *not* done
- an assumption was made in the absence of an answer

---

## 2026-10-02 07:37

**Project initialised.**

Initial plan not yet written.

## 2026-10-02 09:20

**Backend Python is read-only for agents; Track B (B1-B4) goes to the owner**

Owner's standing rule from 2026-09-27; B1 (identity trust, per-route scoping) is the most urgent item overall

## 2026-10-03 05:21

**Previous phase A1-A9 were done on fix/fe-* and fix/stability-pass and merged into main as PR #4 (e824f6c), outside this board; A7 still waits on the owner**

the board was not updated when that work merged; recorded so a later session does not redo it

## 2026-10-03 05:21

**Backend changes are allowed for agents when small and tested; supersedes 'Backend Python is read-only for agents'**

owner approved on 2 Oct and again on 3 Oct (parallel discovery, audit fixes)

## 2026-10-03 05:21

**No stack change: SQLite stays (no Postgres), no new packages**

owner, 3 Oct: 'we don't change the tech stack'
