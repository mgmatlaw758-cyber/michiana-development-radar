# Michiana Development Radar

Local construction and development intelligence for Michiana.

This repository contains the ingestion core for turning public permit reports into
structured, privacy-conscious business intelligence. The first supported source is
the Elkhart County monthly permit export.

## What works

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

Parse a downloaded monthly export:

~~~bash
michiana-radar august-2026-permits.pdf \
  --source-period 2026-08 \
  --output build/elkhart-2026-08.json
~~~

Commercial building permits are exported by default. Add
`--include-noncommercial` for parser QA; those records remain hidden from alerts.

## Build a multi-month database

SQLite is built into Python, so this does not require a database account or server.
Pass the same database path for every monthly report:

~~~bash
michiana-radar build/june-2026-permits.pdf \
  --source-url "https://www.elkhartcountyplanninganddevelopment.com/doc/2026/june-2026-permits.pdf" \
  --source-period 2026-06 \
  --database build/radar.sqlite \
  --output build/elkhart-2026-06.json

michiana-radar build/august-2026-permits.pdf \
  --source-url "https://www.elkhartcountyplanninganddevelopment.com/doc/2026/august-2026-permits.pdf" \
  --source-period 2026-08 \
  --database build/radar.sqlite \
  --output build/elkhart-2026-08.json
~~~

The JSON output includes a `database` section with inserted, updated, unchanged,
stored-permit and stored-project counts. Importing the same report twice should
show zero inserts or updates on the second run.

The `build/` directory and common SQLite file extensions are ignored by Git.
Raw reports, generated JSON and local databases should not be committed.

## Data source

Elkhart County publishes its current monthly permit exports at:

https://www.elkhartcountyplanninganddevelopment.com/Building.html

The importer stores the exact source URL and page numbers with every record.
