# Engineering log

Design decisions, the bugs that shaped them, and what is still weak. Written for someone evaluating the engineering, so it leads with tradeoffs rather than features.

## System shape

```
GitHub Actions (cloud)                     macOS (local, launchd)
──────────────────────                     ──────────────────────────────
monitor.yml     every 2h  ─┐               poll        3 min   queue → native notifications
daily_report    daily      │→ data/*.json  mail-sync   15 min  Apple Mail → application events
tests.yml       on push  ──┘               priority    10 min  program watcher
                                           dashboard   always  Flask :8765, merged tracker view
```

**Workload placement by privilege and latency.** Bursty, parallel, credential-free polling of public job boards runs on ephemeral cloud compute. Anything needing local automation permissions (Mail.app via AppleScript, native notifications) or low-latency reaction runs on the user's machine. The two halves communicate only through JSON files in the repo, so neither can break the other's schedule.

Pipeline (`src/run_monitor.py`): `collect → enrich → dedupe → score → persist → notify`. Scoring is a **deterministic rule engine** (weighted term/regex matches against a profile) — there is no ML model, by choice: every score is explainable and every rejection carries a stated reason.

## Patterns in use (and where they're imperfect)

| Pattern | Where | Honest caveat |
|---|---|---|
| Event-sourcing-lite | `mac/tracker.py` folds mailbox events + queue snapshot + manual overrides into one read model | Events are deduped/merged in place, not an immutable log |
| Multi-source reconciliation with a privileged writer | manual status > latest email event > queue | Precedence is hard-coded, not configurable |
| Order-independent merge | latest `date_iso` wins, ties → stronger stage | Requires normalized timestamps (see below) |
| Tiered/compacted state | `state.py` keeps full payloads only for review-ready jobs | Rescoring a compacted job needs a refetch |
| Write-ahead delivery ledger | `mac/mac_agent.py` `pending → sent`, capped attempts | At-least-once, ≤1 duplicate — exactly-once is impossible with a non-idempotent notifier |
| Health as a sidecar | producers write `*_health.json`; dashboard renders a banner | Surfacing only; no automatic circuit breaking |

## Bugs worth learning from

1. **Locale-formatted dates sorted alphabetically.** Apple Mail returns `"Tuesday, September 8, 2026 at …"`; sorting those strings put "Thursday" after "Tuesday" and let older statuses overwrite newer ones. Fix: normalize every event to `date_iso` and make the status merge commutative instead of relying on iteration order.
2. **Boilerplate is an arms race.** Application receipts contain rejection wording ("unfortunately we cannot respond to everyone"), interview wording ("may reach out to schedule an interview"), and legal disclaimers ("this is *not* an offer of employment"). Whack-a-mole regex per template does not converge. What did: (a) require *decisive* phrases, not sentiment words; (b) when the subject is a plain receipt, only advance the stage on hard present-tense evidence (a scheduled time, an assessment link plus deadline); (c) strip conditional, process-description, and negated sentences before matching.
3. **AppleScript `whose` is O(mailbox size) per call.** Fifteen per-keyword queries per mailbox timed out on large accounts every run. One compound server-side `whose … and (a or b or …)` query per mailbox fixed it. A catch-all "All Mail" folder cannot be scanned in any bounded time — a hard limit of this integration, documented rather than tuned around.
4. **Dedup that hid opportunities.** Keying postings on company+title+location merged distinct requisitions with identical titles (~19% of listings on one run). Posting identity is now `(source, source_id)`; aggregator copies are dropped only when an official posting exists.
5. **Identity without a requisition ID is ambiguous.** Role-less receipts key by submission day so multiple applications to one employer stay visible; role-less status updates route to the company's most recent prior application. Wrong merges hide data; extra rows only clutter — the system errs toward rows.

## Reliability

An independent fault-injection suite (13 cases) found four failures; all are fixed and the suite lives in `tests/test_faults.py`:

- Bounded retry with exponential backoff and `Retry-After` handling for 429/5xx/timeouts; one failing source never blocks the others.
- Requisition-safe dedup (above).
- Write-ahead notification ledger with atomic (temp file + fsync + rename) writes and a two-attempt cap.
- Atomic write for manual statuses — a torn write there would have read back as "empty" and wiped every manual status.

Not covered: power-loss durability, consistency between the separately-replaced state and queue files, load, multi-user use.

## Known limitations

- Mail coverage is Inbox/Archive/job-named folders only; full coverage needs the Gmail/Graph APIs (OAuth).
- The priority-program watcher only fires on employers using supported ATS boards or Simplify listings that match its aliases.
- Graduation-year screening is negative-only (blocks known-bad phrasings; no positive "early-career friendly" signal).
- JSON files as the interchange format are fine at hundreds of rows and would be the first thing to replace at scale.

## Privacy model

Mailbox access is read-only, local, and metadata-oriented: bodies are used transiently for classification and never stored or uploaded. Secrets live in GitHub Actions secrets and the macOS Keychain. Nothing submits an application; autofill helpers fill only whitelisted identity fields and never touch legal, sponsorship, demographic, CAPTCHA, or submit controls.

## Sanitization

This repository was produced from a private one by rewriting history: runtime data (`data/`), account configuration, and internal notes were removed from every commit; personal strings in remaining files were replaced with fictional values; author identities were mapped to a no-reply address. Commit messages, dates, and the sequence of code changes are preserved. About 770 automated state-update commits touched only removed data and no longer appear. Commit IDs differ from the private repository.
