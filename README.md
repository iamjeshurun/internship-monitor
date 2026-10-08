# Internship Job Monitor

A human-in-the-loop internship discovery and application-tracking system: a cloud pipeline that finds and scores postings, plus local macOS services that reconcile application status from your mailbox and notify you. **It never submits an application on your behalf.**

> **Code here, personal data elsewhere.** This repository holds all of the code. A real deployment keeps its personal configuration and job history in a separate private repository and runs this code against it (see [Running a private instance](#running-a-private-instance)). Example configs use fictional values; copy `config/*.example.yaml` and adapt them.

**Quick look (no credentials needed):**

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
pytest -q                 # 109 tests, incl. fault-injection cases
python src/run_monitor.py # polls public boards, scores, writes data/ (notifications skipped without secrets)
```

Architecture, design decisions, reliability findings, and known limitations: **[docs/ENGINEERING_LOG.md](docs/ENGINEERING_LOG.md)**.

---

Cloud discovery on GitHub Actions, native review notifications on macOS, and human-reviewed application preparation. 

## Safety and operating boundary

- Discovery, scoring, queuing, reporting, and notifications can run unattended.
- Application prep can assemble saved answers and open the employer form.
- Login, CAPTCHAs, ambiguous legal/sponsorship questions, and final submission require live review.
- The system never follows, messages, or DMs recruiters automatically.
- Never commit `.env`, OAuth tokens, mailbox exports, or `config/application_answers.yaml`.

## Architecture

1. GitHub Actions polls official Greenhouse, Lever, Ashby, JSON-LD company pages, and Simplify.
2. Jobs are normalized and stored in `data/state.json`; changing the profile can rescore old jobs.
3. Strong eligible matches are published to `data/review_queue.json` and appended to the private `Job Monitor Alerts` GitHub issue.
4. The Mac agent reads the private queue every three minutes and creates native notifications; optional `terminal-notifier` support makes them clickable.
5. The always-on local dashboard at `http://127.0.0.1:8765` replaces the spreadsheet tracker and supports ready, reviewing, applied, assessment, interview, offer, rejected, and dismissed states.
6. `prep_application.py` creates a safe review packet; it never submits.
7. A 15-minute local Apple Mail sync updates tracker stages from Gmail and Outlook/Exchange metadata without retaining message bodies.
8. Optional: a 10-minute local watcher flags named early-career programs (`config/priority_programs.yaml`, e.g. Google STEP) and a daily report (`src/daily_report.py`) summarizes the last 24 hours.

## Quick local test

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
python src/run_monitor.py
JOB_MONITOR_QUEUE_FILE="$PWD/data/review_queue.json" python mac/mac_agent.py
python mac/dashboard.py
```

GitHub issue alerts are the primary cloud notification path. SMTP remains an optional fallback.

## Configure official company boards

Edit `config/sources.yaml`. Every entry must be verified against the employer's official career page.

```yaml
boards:
  greenhouse:
    Example Company: verified_board_token
  lever:
    Example Startup: verified_site_name
  ashby:
    Example Labs: verified_board_name
  custom_pages:
    Example Employer: https://example.com/careers
```

The Simplify source remains enabled for broad discovery. When a Simplify listing
links to a Greenhouse, Lever, or Ashby job URL, the monitor fetches the real job
description (bounded per run) so skill, sponsorship, and graduation screening can
run on it. `sources.yaml → freshness_days` is enforced as a hard block on stale
postings.

## GitHub deployment

1. Create a **private** repository and push this directory.
2. Optional fallback email uses Actions secrets:
   - `SMTP_USER`
   - `SMTP_PASSWORD` (an app password, never the real password)
   - `NOTIFY_EMAIL`
3. Run **Tests**, then manually run **Job Monitor**.
4. Confirm `data/state.json` and `data/review_queue.json` update.
5. Subscribe to the private `Job Monitor Alerts` issue. In GitHub notification settings, enable **Email** and **On GitHub** for **Participating and @mentions** and select a verified destination email.

In this repository the workflow is **manual-only**, so it never posts job matches to a public issue or commits state into a public repository. For scheduled runs, use a private instance (below).

## Running a private instance

Keep personal configuration and job history out of this repository. A private repository needs only:

```
config/   accounts.yaml, resume_profile.yaml, sources.yaml, companies.yaml, priority_programs.yaml
data/     review_queue.json, priority_queue.json (read by the Mac agent)
.github/workflows/   scheduled jobs that check out this repository and run it
```

Every entry point reads `JOB_MONITOR_CONFIG_DIR` and `JOB_MONITOR_DATA_DIR` (defaulting to this repository's `config/` and `data/`), so a private workflow runs the public code against private files:

```yaml
steps:
  - uses: actions/checkout@v7                 # the private repo: config + data
  - uses: actions/checkout@v7
    with: {repository: iamjeshurun/internship-monitor, path: app}
  - run: pip install -r app/requirements.txt
  - run: python app/src/run_monitor.py
    env:
      JOB_MONITOR_CONFIG_DIR: ${{ github.workspace }}/config
      JOB_MONITOR_DATA_DIR: ${{ github.workspace }}/data
```

To deploy to a Mac with private config, pass its folder to the scripts below with `JOB_MONITOR_CONFIG_SOURCE=/path/to/private-repo/config`.

## MacBook notification setup

Run `zsh mac/install.sh`. It installs the small background runtime under `~/Library/Application Support/JobMonitor/runtime`, avoiding macOS background-access restrictions on Documents. For initial testing, use `JOB_MONITOR_QUEUE_FILE` with the local queue. The installer prints commands to save the private repository name under `~/Library/Application Support/JobMonitor/` and the fine-grained read-only token in macOS Keychain. For a one-time foreground test, you may instead set:

```bash
export JOB_MONITOR_GITHUB_REPO="owner/private-repository"
export JOB_MONITOR_GITHUB_TOKEN="fine-grained-read-only-token"
python mac/mac_agent.py
```

Store the token in macOS Keychain or another credential manager before enabling the LaunchAgents. The installer creates the queue poller, always-on dashboard, and 15-minute mailbox sync. The Mac catches up after sleep; the two-hour GitHub search continues while it is offline.

## Existing applications (Apple Mail)

On a Mac with the accounts enabled in Apple Mail, no developer OAuth app is
required. After granting Automation access, scan each account locally:

```bash
python src/email_history.py --provider apple-mail --account your-address@example.com
```

The importer records inferred company, stage, date, requisition ID, and confidence. It intentionally does not store full message bodies. The installed Mac mailbox service performs this scan every 15 minutes across all accounts in `JOB_MONITOR_MAIL_ACCOUNTS` (comma-separated addresses as configured in Mail.app), or, if that is unset, `application_history.mail_accounts` in `config/accounts.yaml`. There is no default. Each run scans a short rolling window (`JOB_MONITOR_MAIL_DAYS`, default 21) of the **Inbox and Archive only** — never Gmail's "All Mail", which cannot be scanned within any timeout — using one compound Mail query per mailbox; prior events are merged forward for ~365 days so history is not lost. Per-account scan health is written to `mail_health.json` and surfaced on the dashboard. OAuth application registration and refresh-token custody must be completed for a non-Apple-Mail connection; do not place tokens in GitHub.

### Redeploying code to the running Mac

```bash
zsh scripts/deploy_runtime.sh
```

Syncs `src/`, the Mac scripts, and behaviour config into `~/Library/Application Support/JobMonitor/runtime` and restarts the dashboard. With `JOB_MONITOR_CONFIG_SOURCE=/path/to/private-repo/config`, config (including `accounts.yaml`) comes from the private repository; without it, account routing is never overwritten. Run `mac/install.sh` instead when dependencies or the LaunchAgent plists change.

## Application preparation

```bash
mkdir -p ~/.config/job-monitor
cp config/application_answers.example.yaml ~/.config/job-monitor/application_answers.yaml
# Complete the private copy, then:
python src/prep_application.py JOB_KEY
```

The generated packet separates safe saved answers from questions requiring review. Use the employer's real form in a live browser session; review every field and submit only after confirming the specific application.

### Optional live-browser autofill

`safari/job-monitor-autofill.user.js` runs through the lightweight Userscripts app; Xcode is not required. Save only basic identity fields, then click **Review Autofill** while reviewing an application. Teal fields were filled automatically; orange fields require review. It has no submit capability and stores its small identity profile only in the userscript manager. Do not place passwords, government identifiers, or demographic answers in it.

## License

MIT — see [LICENSE](LICENSE).

## Interactive dashboard and public demo

The dashboard uses the same interface in two modes:

- **Public demo:** `web/` contains a static site with 16 explicitly fictional records. Board, table, activity, search, stage filters, match explanations, priority labels and status changes work in the browser. Reloading or choosing **Reset demo** restores the fixtures. It never calls a local tracker, a mailbox, or a remote API.
- **Local tracker:** `python mac/dashboard.py` serves that interface at `http://127.0.0.1:8765`. It reads the existing queue, mailbox history and manual statuses, and saves changes through Flask. Mailbox/agent health warnings remain visible. Records refresh every minute while the page is visible and no detail panel is open, or on **Refresh records**.

Preview the public demo from the repository root:

```sh
python scripts/build_demo.py
python -m http.server 8795 --bind 127.0.0.1 --directory web
```

Open `http://127.0.0.1:8795`. This is a local preview, not a published demo URL. The `web/` directory is ready for static hosting, including GitHub Pages under a repository subpath; publishing is a separate step. Do not upload the repository root or local runtime data.

The opening uses current-stage counts, not a claim about past stage transitions. Decorative motion repeats every five seconds while the opening is visible, pauses in background tabs, supports a pause control, and respects reduced-motion preferences. Activity dates are mailbox-message dates, not interview appointments. Match scores describe profile fit, not hiring probabilities.

The demo is generated only from `demo/fixtures.json` through the real `merge_tracker()` function; the builder never reads `JOB_MONITOR_LOCAL_DIR` or personal files. Run `python scripts/build_demo.py --check` to verify the committed bootstrap matches those fixtures. Edit the fixtures and regenerate instead of editing `web/bootstrap.js`.

The local JSON interface is `GET /api/tracker` and `POST /api/status/<key>`. Saves require the current browser session's CSRF token from `/bootstrap.js`, a known record key and one of the eight supported stages. The existing form route `/status/<key>` remains available with a `csrf_token` field. Ready/Reviewing remain subject to existing mailbox-stage precedence; the UI displays the resolved backend state after a save. The local service stays bound to loopback and is not a public multi-user backend.

`mac/install.sh` and `scripts/deploy_runtime.sh` copy the shared `web/` assets into the local runtime. They should be run only when you intend to update that installed instance.

Validation:

```sh
python -m pytest tests -q
node --test tests/frontend.test.mjs
python scripts/build_demo.py --check
```

The frontend tests compare all 128 demo record/status combinations against the actual Python merger, including mailbox-only records, manual precedence, preserved mailbox events and safe rendering of untrusted text/links. Node 22+ is needed for these tests, not to run or host the dashboard.
