# Michiana Development Radar

Local construction and development intelligence for Michiana.

This repository turns public permit reports into structured, privacy-conscious
business intelligence. The first supported source is the Elkhart County monthly
permit export.

## What works

- Discover all published Elkhart monthly permit reports for a selected year
- Safely download and cache official county PDFs
- Extract permit pages from an Elkhart County PDF
- Merge adjacent continuation pages that repeat a permit number
- Parse dates, values, descriptions, locations, parcels and business contractors
- Drop phone numbers, email addresses and party mailing addresses from output
- Hide residential owner identities
- Retain source URL, reporting period and page provenance
- Group probable companion permits without grouping solely by dollar value
- Persist multiple months in SQLite without duplicating repeated imports
- Rebuild project groups across every stored reporting period
- Keep an import ledger and every permit source observation
- Browse a searchable local project feed with city, type and value filters
- Open the original county source PDF for every displayed permit
- Open a dedicated record page for each project and copy its direct link
- Preserve project IDs when later companion permits join an existing project
- Verify behavior against redacted fixtures derived from real August 2026 permits

## Product boundary

The initial product is commercial market intelligence. It is not a homeowner
telemarketing list. Personal contact information is neither emitted by the parser
nor written to exported records.

## Quick start

Requires Python 3.11 or newer.

~~~bash
python -m venv .venv
python -m pip install -e ".[dev]"
pytest
~~~

## Open the project feed

After importing permit reports, launch the private local dashboard:

~~~bash
michiana-radar serve --database build/radar.sqlite
~~~

Open http://localhost:8000 in a browser. In GitHub Codespaces, use the
notification to open port 8000 or select port 8000 from the **Ports** panel.

The dashboard searches descriptions, addresses, permit numbers, contractors,
business names and parcel numbers. It can also filter by city, project type and
minimum listed permit value. Select a project title to open its dedicated record
page. That page includes every grouped permit, parcel and zoning details, plus a
link to the exact page in the original county PDF. Project IDs are retained when
future imports add an ordinary companion permit to an existing project.

The server binds to 127.0.0.1 by default and does not alter the database.

## Synchronize a full year

Discover, download and import every currently published Elkhart County monthly
permit report for a year with one command:

~~~bash
michiana-radar sync-elkhart \
  --year 2026 \
  --database build/radar.sqlite \
  --output build/sync-elkhart-2026.json
~~~

Downloads are cached under build/source-cache/elkhart/2026/. Run the command
again to reuse those files and test idempotency. Add --refresh when the county
has replaced a previously published PDF and a fresh download is required.

The synchronization summary lists every discovered month, download status, record
counts and any individual failures. A partial failure returns a nonzero exit code
without discarding months that imported successfully.

The downloader only accepts HTTPS PDF links on the official Elkhart County
Planning and Development host. Raw reports, generated JSON and SQLite databases
remain under ignored paths and should not be committed.

## Parse one report manually

~~~bash
michiana-radar build/august-2026-permits.pdf \
  --source-url "https://www.elkhartcountyplanninganddevelopment.com/doc/2026/august-2026-permits.pdf" \
  --source-period 2026-08 \
  --database build/radar.sqlite \
  --output build/elkhart-2026-08.json
~~~

Commercial building permits are exported by default. Add
--include-noncommercial for parser QA; those records remain hidden from the
project feed.

The JSON output includes a database section with inserted, updated, unchanged,
stored-permit and stored-project counts. Importing the same report twice should
show zero inserts or updates on the second run.

SQLite is built into Python, so this does not require a database account or server.
The build/ directory and common SQLite file extensions are ignored by Git.

## Data source

Elkhart County publishes its current monthly permit exports at:

https://www.elkhartcountyplanninganddevelopment.com/Building.html

The importer stores the exact source URL and page numbers with every record.
