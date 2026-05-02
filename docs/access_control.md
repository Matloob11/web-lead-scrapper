# Supabase Access Control

This project now checks Supabase before the CLI, desktop dashboard, manual browser helper, or outreach/export jobs can run.

## Files

- App gate: `scraper/access_control.py`
- Connection test: `python -m tools.test_supabase_connection`
- Project env: `.env`
- Standalone admin panel: `../matloob_admin_panel`
- Supabase schema/RPC: `../matloob_admin_panel/schema.sql`

## Setup

1. Open Supabase SQL Editor.
2. Run `../matloob_admin_panel/schema.sql`.
3. Confirm `matloob data scrap/.env` contains:

```text
SUPABASE_URL=https://mgkutjhpymxnwxuroiqa.supabase.co
SUPABASE_KEY=sb_publishable_7OlemOZKSMPkLC-jk17XgA_LN61piRc
```

4. Test the app-side DB/RPC connection:

```powershell
.\.venv\Scripts\python.exe -m tools.test_supabase_connection
```

First run should create a pending request in Supabase. The app will stay blocked until admin approves it.

## Admin Panel

The admin panel is intentionally outside this project folder:

```text
../matloob_admin_panel
```

Edit `../matloob_admin_panel/.env` and set:

```text
SUPABASE_SERVICE_ROLE_KEY=<your Supabase service role key>
ADMIN_PASSWORD=<strong local admin password>
FLASK_SECRET_KEY=<random secret>
```

Then run:

```powershell
cd ..\matloob_admin_panel
..\matloob data scrap\.venv\Scripts\python.exe app.py
```

Open:

```text
http://127.0.0.1:5055
```

## Behavior

- `approved`: app continues.
- `pending`: app stops and tells the user request is waiting for approval.
- `rejected`: app stops.
- `blocked`: app stops.
- DB/network/schema/package issue: app stops with a technical error.

The app uses the publishable key only. Approve/reject/block actions require the service-role key in the separate admin panel.
