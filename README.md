# Internship Job Monitor v2

Cloud discovery on GitHub Actions, native review notifications on macOS, and human-reviewed application preparation. This upgrades the original Claude prototype without carrying forward guessed Greenhouse boards, unsafe private answers, or the one-way `seen_jobs.json` design.

## Safety and operating boundary

- Discovery, scoring, queuing, reporting, and notifications can run unattended.
- Application prep can assemble saved answers and open the employer form.
- Login, CAPTCHAs, ambiguous legal/sponsorship questions, and final submission require live review.
- The system never follows, messages, or DMs recruiters automatically.
- Never commit `.env`, OAuth tokens, mailbox exports, or `config/application_answers.yaml`.

## Architecture

1. GitHub Actions polls official Greenhouse, Lever, Ashby, JSON-LD company pages, Simplify, and optional X search.
2. Jobs are normalized and stored in `data/state.json`; changing the profile can rescore old jobs.
3. Strong eligible matches are published to `data/review_queue.json` and emailed.
4. The Mac agent reads the private queue every three minutes and creates native notifications.
5. The local dashboard at `http://127.0.0.1:8765` supports review, dismiss, and applied states.
6. `prep_application.py` creates a safe review packet; it never submits.
7. `email_history.py` imports prior application evidence from Outlook, Gmail, or exported `.eml` files.

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

With no SMTP credentials, email is skipped visibly while the review queue remains durable.

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

The Simplify source remains enabled for broad discovery. It has no job descriptions, so its results are explicitly flagged for sponsorship and qualification review.

## GitHub deployment

1. Create a **private** repository and push this directory.
2. Add Actions secrets:
   - `SMTP_USER`
   - `SMTP_PASSWORD` (an app password, never the real password)
   - `NOTIFY_EMAIL`
   - `X_BEARER_TOKEN` only if X monitoring is enabled
3. Run **Tests**, then manually run **Job Monitor**.
4. Confirm `data/state.json` and `data/review_queue.json` update.
5. Confirm an `ACTION READY` email reaches the phone mail app.

The monitor runs at minutes 7 and 37 each hour, uses a concurrency lock, and commits only durable state files. Tests run on code changes, not every polling cycle.

## MacBook notification setup

Run `zsh mac/install.sh`. For initial testing, use `JOB_MONITOR_QUEUE_FILE` with the local queue. The installer prints commands to save the private repository name under `~/Library/Application Support/JobMonitor/` and the fine-grained read-only token in macOS Keychain. For a one-time foreground test, you may instead set:

```bash
export JOB_MONITOR_GITHUB_REPO="owner/private-repository"
export JOB_MONITOR_GITHUB_TOKEN="fine-grained-read-only-token"
python mac/mac_agent.py
```

Store the token in macOS Keychain or another credential manager before enabling the LaunchAgent. The Mac catches up after sleep; GitHub continues searching while it is offline.

## Outlook, Gmail, and existing applications

Privacy-first option: export job confirmations as `.eml` files, then run:

```bash
python src/email_history.py --eml-dir /path/to/exported/job-mail
```

API options require short-lived OAuth access tokens with read-only mail scope:

```bash
OUTLOOK_ACCESS_TOKEN=... python src/email_history.py --provider outlook
GMAIL_ACCESS_TOKEN=... python src/email_history.py --provider gmail
```

On a Mac with the accounts enabled in Apple Mail, no developer OAuth app is
required. After granting Automation access, scan each account locally:

```bash
python src/email_history.py --provider apple-mail --account your-address@example.com
```

The importer records inferred company, stage, date, requisition ID, and confidence. It intentionally does not store full message bodies. OAuth application registration and refresh-token custody must be completed for a permanent connection; do not place tokens in GitHub.

## X internship and recruiter leads

Set `sources.x.enabled: true`, tune its query, and add `X_BEARER_TOKEN` to GitHub Actions. X results enter the same queue as social leads. Recruiter outreach remains a reviewable draft workflow, not an automatic messaging system.

## Application preparation

```bash
mkdir -p ~/.config/job-monitor
cp config/application_answers.example.yaml ~/.config/job-monitor/application_answers.yaml
# Complete the private copy, then:
python src/prep_application.py JOB_KEY
```

The generated packet separates safe saved answers from questions requiring review. Use the employer's real form in a live browser session; review every field and submit only after confirming the specific application.

### Optional live-browser autofill

`browser-extension/` is the Chromium helper. Safari users can use `safari/job-monitor-autofill.user.js` through the lightweight Userscripts app; Xcode is not required. Save only basic identity fields, then click **Review Autofill** while reviewing an application. Teal fields were filled automatically; orange fields require review. It has no submit capability and stores its small identity profile only in the userscript manager. Do not place passwords, government identifiers, or demographic answers in it.

## Files retained from Claude

- The tested Simplify HTML-table parser.
- The real Simplify snapshot fixture and parser tests.
- The 144-company watchlist, résumé-derived skill vocabulary, and basic provider approach.

## Replaced from Claude

- Guessed board tokens.
- Permanent one-way seen list.
- California down-ranking.
- Missing US filtering.
- Silent email success.
- Spreadsheet-only state and incomplete daily reports.
- Sensitive application answers stored inside the repository.
