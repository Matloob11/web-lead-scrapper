# Houzz Pro Scraper

Run the scraper from the project root.

```powershell
.\.venv\Scripts\python.exe houzz_pro_scraper.py --url "HOUZZ_SEARCH_URL" --country USA
```

Desktop dashboard:

```powershell
.\.venv\Scripts\python.exe gui_app.py
```

When no `--source` is passed, the main file asks:

```text
1) Houzz
2) BBB
```

BBB example:

```powershell
.\.venv\Scripts\python.exe houzz_pro_scraper.py --source bbb --url "BBB_SEARCH_URL" --max-pages 1
```

Output rules:

- Duplicate emails are skipped in each source master CSV.
- Detail rows are unique per `email + profile URL`.
- Profiles are processed only when they look contractor, construction, home-improvement, architecture, property, or real-estate related.
- Final quality-filtered exports are written to `final/` after scraping, or manually with `--export-final-only`.

Final export examples:

```powershell
.\.venv\Scripts\python.exe houzz_pro_scraper.py --source bbb --export-final-only
```

```powershell
.\.venv\Scripts\python.exe houzz_pro_scraper.py --source houzz --export-final-only --quality-filter high
```

Automated QA:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q houzz_pro_scraper.py scraper tools tests
```

Short live smoke test:

```powershell
.\.venv\Scripts\python.exe houzz_pro_scraper.py --source bbb --url "BBB_SEARCH_URL" --max-pages 1 --max-profiles 1 --no-final-export
```

Project layout:

- `houzz_pro_scraper.py` - root main file and CLI.
- `houzz_emails.csv` - root Houzz master email CSV.
- `bbb_emails.csv` - root BBB master email CSV.
- `desktop_app/` - dashboard UI, background services, and data summaries.
- `scraper/` - all scraper code modules.
- `scraper/sources/` - Houzz, website, and Facebook scraping workflows.
- `scraper/sources/bbb_profile.py` - BBB search/profile workflow.
- `scraper/search/` - Google Facebook fallback.
- `scraper/filters/` - email extraction and validation.
- `scraper/storage/` - CSV, status, and log writers.
- `output/csv/` - separate detailed CSV and scrape status files.
- `output/logs/` - failure logs.
- `runtime/user_data/` - persistent browser profile/session.
- `tools/login_helper.py` - opens the persistent browser profile for manual login.
- `setup/requirements.txt` - Python dependencies.

Manual login helper:

```powershell
.\.venv\Scripts\python.exe tools\login_helper.py
```
