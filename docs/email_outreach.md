# Compliant Email Outreach

This project includes a compliant outreach module for a registered construction
company. It is designed for deliverability, consent, and auditability. It does
not bypass inbox protections or force mail to suppressed, bounced, invalid,
duplicate, or unconfirmed contacts.

## Sender Setup

Store SMTP credentials in environment variables before sending:

```powershell
$env:MATLOOB_SMTP_HOST="smtp.gmail.com"
$env:MATLOOB_SMTP_PORT="587"
$env:MATLOOB_SMTP_USERNAME="sender@yourdomain.com"
$env:MATLOOB_SMTP_PASSWORD="<app password or SMTP password>"
$env:MATLOOB_FROM_EMAIL="sender@yourdomain.com"
$env:MATLOOB_FROM_NAME="Matloob Construction"
$env:MATLOOB_REPLY_TO="reply@yourdomain.com"
```

Use a company domain whenever possible. Personal Gmail accounts are poor long-term
senders for business outreach and make domain reputation harder to manage.

## DNS Checklist

Set these records at your domain DNS provider:

- SPF: include every provider that sends mail for the domain.
- DKIM: enable 2048-bit DKIM when supported by the mail provider.
- DMARC: start with `p=none` and reports, then move gradually toward stricter
  policy after legitimate mail passes consistently.
- TLS: send through an SMTP provider that supports TLS.
- Forward and reverse DNS: required for dedicated sending infrastructure.

Google's sender guidelines require SPF or DKIM for all senders, and SPF, DKIM,
DMARC, alignment, visible unsubscribe, and one-click unsubscribe for large bulk
senders. The FTC CAN-SPAM guide requires truthful sender information, accurate
subjects, a physical address, opt-out, and honoring opt-outs.

## Contact Rules

The outreach system reads CSV files with these optional columns:

```csv
Email,Name,City,Project Type,Company,Permission Status
owner@example.com,Sam,Dallas,kitchen remodel,Example Builders,verified
```

Allowed permission values include `verified`, `opt_in`, `confirmed`,
`subscribed`, `permission`, and `manual_confirmed`.

If a CSV only contains `Email`, contacts are treated as unknown permission unless
the dashboard operator explicitly checks `Permission Confirmed`. Every recipient
is still recorded in the audit report as sent, dry-run ready, invalid,
suppressed, duplicate, already sent, high risk, or missing permission.

Outreach imports are intentionally restricted to email export files only:

- Project root: `houzz_emails.csv`, `bbb_emails.csv`, or another `*_emails.csv`
  master export.
- Final folder: `final/*_emails.csv`.

The sender rejects status files, log files, detail files, duplicate reports,
Google fallback status files, and CSVs outside the project folder. The sent
ledger also blocks an email address globally after a successful send, even if a
later campaign uses a different campaign ID.

## Sending Workflow

1. Export high-quality emails from the scraper.
2. Open the dashboard with `python gui_app.py`.
3. Go to `Email Outreach`.
4. Select the contacts CSV.
5. Fill company name, physical address, unsubscribe URL, subjects, and body.
6. Keep `Dry Run` checked and click `Analyze`.
7. Fix blocked issues and risky copy.
8. Uncheck `Dry Run` only when the audit looks correct.

Local state is stored in `runtime/outreach/`:

- `suppression_list.csv`
- `sent_ledger.csv`
- `tracking_events.csv`

These files are ignored by Git because they contain recipient data.

## Warming Strategy

Start with people who expect your email and are likely to reply. Use one sender
identity, consistent company branding, and plain text. A conservative ramp:

- Week 1: 10-20/day, no automation-heavy wording.
- Week 2: 25-40/day if bounce and complaint rates stay low.
- Week 3: 50-75/day only if replies and engagement are healthy.

Stop or reduce sending if bounces rise, if recipients complain, or if Gmail
Postmaster Tools reports spam rate near 0.3%.

## Construction Email Style

Good construction outreach feels specific and useful:

- Mention the city or project type naturally.
- Offer a small useful next step: estimate checklist, site visit, scope review.
- Keep the first email under 120 words.
- Avoid hype: `act now`, `guaranteed`, `cheapest`, `limited time`, `free`.
- Ask one simple question.
- Include your company name, physical address, and unsubscribe link.

Example:

```text
Hi {name},

I noticed you may have construction or remodeling needs in {city}. We are a
registered construction company and can help with estimates, planning, and
reliable crew scheduling for {project_type} work.

Would it be useful if I sent a short estimate checklist?

Thanks,
{company_name}
```
