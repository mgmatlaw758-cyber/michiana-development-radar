# Michiana Development Radar

Local construction and development intelligence for Michiana.

This repository contains the ingestion core for turning public permit reports into
structured, privacy-conscious business intelligence. The first supported source is
the Elkhart County monthly permit export.

## Current scope

- Parse Elkhart County permit PDFs page by page
- Merge continuation pages that repeat the same permit number
- Normalize commercial building permit fields
- discard phone numbers, email addresses and party mailing addresses
- hide residential owner identities
- retain source provenance for every record
- group probable companion permits into projects
- test against redacted fixtures derived from real August 2026 permits

## Product boundary

The initial product is commercial market intelligence. It is not a homeowner
telemarketing list. Personal contact information is neither emitted by the parser
nor written to exported records.

## Status

Initial implementation in progress.
