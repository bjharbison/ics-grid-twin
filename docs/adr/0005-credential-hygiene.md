# ADR-0005: Credentials out of the repo; rotate what leaked

**Status:** Accepted · **Date:** 2026-07-15

## Context

Early reference documents carried live credentials in plaintext — an InfluxDB
admin token, broker and Grafana passwords. Those documents are the source
material for this repo. Anything that sat in plaintext must be treated as
compromised.

## Decision

1. **Nothing secret in the repo.** All credentials come from `.env` /
   `secrets.h` (both gitignored), sourced from Vaultwarden at config time.
   Templates (`.env.example`, `secrets.h.example`, `acl.example`) ship with
   placeholders only.
2. **Pre-commit secret scanning is a hard gate** (`gitleaks` +
   `detect-private-key`). See `.pre-commit-config.yaml`.
3. **Rotate the previously-exposed credentials** regardless of scrub — the
   InfluxDB admin token especially. A scrub removes them from *future* commits;
   it does nothing for values already seen in plaintext.

## Consequence

The repo is publishable. The rotation step is a release checklist item, not an
optional cleanup — the two actions (scrub, rotate) are independent and both
required.
