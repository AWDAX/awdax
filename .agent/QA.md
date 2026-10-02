# QA — AWDAX

> **Responsibility:** what was checked, how, and what the result was.
> Append-only, written by the verification gates. This is the evidence trail:
> if a task is marked DONE, the proof is here.
>
> `STATUS.md` says *whether* something is verified. This says *how*.

Each entry records:

- the task and the code state it was verified against
- which classes ran — CODE, RUNTIME, UI
- the verdict per class: PASS / FAIL / UNVERIFIED
- for UI: console errors, failed requests, viewports, screenshots

`UNVERIFIED` is a real result. A check that could not run is never recorded
as passing.

---

_No verification recorded yet._
