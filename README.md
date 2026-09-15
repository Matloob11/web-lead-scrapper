# Web Lead Scraper

Playwright scraper for contractor and real-estate emails on **Houzz** and **BBB**, plus a desktop dashboard (`gui_app.py` → `desktop_app/`) with a compliant Email Outreach page.

CLI and dashboard both require **Supabase device approval**. If the device is pending, rejected, blocked, or Supabase is unreachable, the process exits with a clear error.

The approval admin UI is a separate project (`../matloob_admin_panel`), not this repo.

## Features

- Houzz and BBB scrapers with resume/status CSVs
- Quality scoring and `--quality-filter high`
- `--export-final-only` (rebuild client CSVs without a new scrape)
- Desktop dashboard + SMTP outreach (dry-run, template preview, suppression/sent ledger)
- Connection check: `python -m tools.test_supabase_connection`

See `docs/access_control.md` and `docs/email_outreach.md`.

## Output

- `houzz_emails.csv` / `bbb_emails.csv`
- `output/csv/*_results_detailed.csv`
- `output/csv/*_scrape_status.csv`
- `final/*_high_quality_emails.csv`

Scraped emails, logs, browser profiles, and `.venv` are gitignored.

## Stack

- Python 3.11 (ruff in `pyproject.toml`)
- Playwright Chromium
- CustomTkinter / Qt desktop (`desktop_app/`)
- Supabase access gate

## Environment

`.env.example`:

```env
SUPABASE_URL=
SUPABASE_KEY=
```

Outreach is **not** in `.env.example`. Set process env (never commit passwords):

```powershell
$env:MATLOOB_SMTP_HOST="smtp.example.com"
$env:MATLOOB_SMTP_PORT="587"
$env:MATLOOB_SMTP_USERNAME="sender@yourdomain.com"
$env:MATLOOB_SMTP_PASSWORD="<app password>"
$env:MATLOOB_FROM_EMAIL="sender@yourdomain.com"
$env:MATLOOB_FROM_NAME="Your Company"
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install -r setup\requirements.txt
.\.venv\Scripts\playwright.exe install chromium
copy .env.example .env
```

## Run

```powershell
.\.venv\Scripts\python.exe houzz_pro_scraper.py
.\.venv\Scripts\python.exe gui_app.py

.\.venv\Scripts\python.exe houzz_pro_scraper.py --source houzz --url "HOUZZ_SEARCH_URL"
.\.venv\Scripts\python.exe houzz_pro_scraper.py --source bbb --url "BBB_SEARCH_URL"
.\.venv\Scripts\python.exe houzz_pro_scraper.py --source bbb --export-final-only
.\.venv\Scripts\python.exe houzz_pro_scraper.py --source houzz --export-final-only --quality-filter high
```

Manual browser helper:

```powershell
.\.venv\Scripts\python.exe tools\open_browser.py --url "https://www.bbb.org/"
```

Respect Houzz and BBB terms of use.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q houzz_pro_scraper.py scraper tools tests
```

Short BBB smoke:

```powershell
.\.venv\Scripts\python.exe houzz_pro_scraper.py --source bbb --url "BBB_SEARCH_URL" --max-pages 1 --max-profiles 1 --no-final-export
```

## Layout

```text
houzz_pro_scraper.py
gui_app.py
scraper/
desktop_app/
setup/requirements.txt
docs/
tools/
tests/
output/  final/
```

## License

See the repository.
