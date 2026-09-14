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
- Verify behavior against redacted fixtures derived from real August 2026 permits

## Product boundary

The initial product is commercial market intelligence. It is not a homeowner
telemarketing list. Personal contact information is neither emitted by the parser
nor written to exported records.

## Quick start

Requires Python 3.11 or newer.

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
pytest
```

Parse a downloaded monthly export:

```bash
michiana-radar august-2026-permits.pdf \
  --source-period 2026-08 \
  --output build/elkhart-2026-08.json
```

Commercial building permits are exported by default. Add
`--include-noncommercial` for parser QA; those records remain hidden from alerts.

## Data source

Elkhart County publishes its current monthly permit exports at:

https://www.elkhartcountyplanninganddevelopment.com/Building.html

The importer stores the exact source URL and page numbers with every record.
