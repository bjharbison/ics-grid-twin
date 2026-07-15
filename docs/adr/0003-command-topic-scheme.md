# ADR-0003: Canonical command-topic scheme (drift caught pre-release)

**Status:** Accepted · **Date:** 2026-07-15

## Context

Two firmware generations existed in project history:

* an earlier build using `fleet/<id>/cmd` with JSON `{"action":"set_role",...}`
  and `esp32-<mactail>` board ids;
* the validated `universal_field.ino` (the one flashed to all six boards and
  proven with an end-to-end breaker-trip test) using **`cmd/<short>/<verb>`**
  with bare-string payloads and `grid-substation-<mactail>` identity.

An existing fleet-manager GUI had been written against the **earlier** scheme.
Rebuilding it for V1 surfaced the mismatch: had it shipped unchanged, it would
have connected, displayed telemetry correctly (the read path is scheme-agnostic
— it subscribes `#`), and then **silently failed on every command**, publishing
to `fleet/<id>/cmd` while the boards listen on `cmd/<short>/#`.

This is the same silent-failure class the lab hit once before: `esp32-field`
had MQTT write rules but no `topic read cmd/#`, so commands published cleanly,
returned success, and were never delivered — nothing logged on either end.

## Decision

Standardize the entire repo — firmware, fleet manager, ACL, docs — on the
validated **`cmd/<short>/#`** scheme:

```
cmd/<short>/breaker   "open" | "close"
cmd/<short>/role      "<rolename>"
cmd/all/<verb>        broadcast
```

The earlier `fleet/#` scheme is retired. The fleet manager surfaces the silent-
delivery risk directly: after any publish it logs that a clean publish only
proves *broker acceptance*, and the effect must be confirmed in telemetry.

## Consequence

The whole toolchain speaks one command language, matching what is flashed.
The class of bug that bit the lab once is now called out in code and docs at
the exact point it would recur.
