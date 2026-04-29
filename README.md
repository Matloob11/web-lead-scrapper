# Web Lead Scraper

Python Playwright scraper for collecting contractor and real-estate related emails from Houzz and BBB.

## Run

```powershell
.\.venv\Scripts\python.exe houzz_pro_scraper.py
```

Desktop dashboard:

```powershell
.\.venv\Scripts\python.exe gui_app.py
```

The dashboard also includes a compliant Email Outreach page for dry-run analysis,
template preview, suppression/sent-ledger checks, and SMTP sending through
environment variables. See `docs/email_outreach.md`.

Or run a source directly:

```powershell
.\.venv\Scripts\python.exe houzz_pro_scraper.py --source houzz --url "HOUZZ_SEARCH_URL"
```

```powershell
.\.venv\Scripts\python.exe houzz_pro_scraper.py --source bbb --url "BBB_SEARCH_URL"
```

Direct CLI runs use the same MongoDB admin approval rules as the desktop dashboard. The
app creates an automatic device ID, sends it to the admin panel, and waits for approval.
For support/testing, override it with `--device-id` or the `MATLOOB_DEVICE_ID`
environment variable.

## Output

- `houzz_emails.csv` - clean Houzz email list
- `bbb_emails.csv` - clean BBB email list
- `output/csv/*_results_detailed.csv` - detailed rows with quality scoring
- `output/csv/*_scrape_status.csv` - resume/status tracking
- `final/*_high_quality_emails.csv` - final quality-filtered client-ready emails
- `desktop_app/` - desktop dashboard app, run services, and UI components

Scraped emails, logs, browser profiles, and virtualenv files are ignored by Git.

Export final files without scraping:

```powershell
.\.venv\Scripts\python.exe houzz_pro_scraper.py --source bbb --export-final-only
```

Choose quality levels:

```powershell
.\.venv\Scripts\python.exe houzz_pro_scraper.py --source houzz --export-final-only --quality-filter high
```

## Test and Debug

Run the automated checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q houzz_pro_scraper.py scraper tools tests
```

Validate export files without scraping:

```powershell
.\.venv\Scripts\python.exe houzz_pro_scraper.py --source bbb --export-final-only
.\.venv\Scripts\python.exe houzz_pro_scraper.py --source houzz --export-final-only
```

Short BBB smoke test:

```powershell
.\.venv\Scripts\python.exe houzz_pro_scraper.py --source bbb --url "BBB_SEARCH_URL" --max-pages 1 --max-profiles 1 --no-final-export
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install -r setup\requirements.txt
.\.venv\Scripts\playwright.exe install chromium
```

MongoDB admin approval requires a connection URI in the environment. Do not commit
real credentials into the codebase:

```powershell
$env:MATLOOB_MONGO_URI="<your MongoDB connection URI>"
```

Email outreach credentials must also stay out of source code:

```powershell
$env:MATLOOB_SMTP_HOST="smtp.gmail.com"
$env:MATLOOB_SMTP_PORT="587"
$env:MATLOOB_SMTP_USERNAME="sender@yourdomain.com"
$env:MATLOOB_SMTP_PASSWORD="<app password or SMTP password>"
$env:MATLOOB_FROM_EMAIL="sender@yourdomain.com"
$env:MATLOOB_FROM_NAME="Matloob Construction"
```

Manual browser/VPN setup:

```powershell
.\.venv\Scripts\python.exe tools\open_browser.py --url "https://www.bbb.org/"
```
