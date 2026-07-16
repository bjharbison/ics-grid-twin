# ADR-0011: Merge the 2.5D/3D twin build; four corrections found during integration

**Status:** Accepted · **Date:** 2026-07-16

## Context

A more capable twin build existed outside this repo — combined 2.5D isometric
(SVG) and 3D (`three.js`) views behind one mode toggle, sharing one physics
state object, plus a live MQTT source, an InfluxDB replay source (CSV paste or
query, via a same-origin backend proxy or direct-with-warnings), and a
`twin3d-kit.js` companion extracting the lighting/orbit-nav code so future
twins (water, datacenter, pipeline) inherit it instead of re-deriving it. This
matches what project memory already described as the intended three-mode twin
architecture.

This supersedes the simpler single-view `twin/grid_twin.html` built for the V1
push (ADR-0001 through ADR-0010) with something both more capable and, in
several respects, more correct.

## What was verified before merging

- Breaker polarity: `1 = closed`, `0 = open` — correct
- Signature: voltage holds, current/power collapse on trip — correct, confirmed
  numerically
- Read-only: zero `.publish()` calls, zero `localStorage`/`sessionStorage`
- Command topics (`cmd/#`) excluded from telemetry ingestion
- Status handled as a bare string (LWT), not JSON
- Tolerant `_phase_` → canonical tag folding (independent evidence the build
  already incorporated the ADR-0002 correction)
- `twin3d-kit.js`'s lighting defaults are byte-identical to what the twin used
  inline — a faithful extraction, not a drifted rewrite

## Four corrections made during integration

1. **Load estimator was current-based, not voltage-based.** Same class of bug
   as the original V1 build: current collapses to ~0 on a trip, so a
   current-based estimate reads "zero load" during the exact event being
   demoed. Fixed to invert voltage sag instead, which holds through a trip.
   Requested explicitly before merging.

2. **Frequency was coupled to load** (`60.0 - 0.05*load`). Firmware treats
   frequency as an independent bounded random walk toward 60.00 Hz — this is
   the exact error ADR-0002 already corrected once, reintroduced here by a
   separate build reaching the same wrong conclusion independently. Replaced
   with a bounded random walk matching firmware's actual behavior.

3. **Transformer thermal target was current-based** (`50 + 35*clamp(iAvg/350)`)
   instead of load-based. Consequence, not just a style difference: at full
   **normal** load with the breaker closed, this reached **85°C** — exceeding
   the documented 80°C alarm threshold under completely benign conditions,
   contradicting the established "red band is unreachable from load alone"
   claim. Replaced with firmware's load-based, breaker-gated formula
   (`45 + 30*ld`), which correctly caps at ~75°C under max normal load and
   cools to ambient on a trip.

4. **Status parsing dropped a defensive guard during my own rewrite.** Adding
   the multi-feeder picker required rewriting `ingest()`; the rewrite
   collapsed the original's `if(s==='online'||s==='offline')` guard so that
   any unrecognized status payload was silently treated as "offline" rather
   than ignored. Caught by comparing the new code against the file's own
   prior behavior before shipping, not by a user hitting it. Restored.

Power factor coefficients (`0.99 - 0.09*load` vs. firmware's `0.985 - 0.06`)
were also corrected to match exactly, consistent with the project's standing
practice of exact constant fidelity rather than "close enough."

## What was added

**Multi-feeder picker.** The original build assumed a single board on topic
root `grid/#`; subscribing there with six real boards live would blend all six
feeders' data with no way to tell whose numbers were on screen. Added: board
discovery from `grid/+/status`, a feeder dropdown, auto-select on first
discovery, and telemetry filtering so only the selected board's tags update the
view. Switching feeders forces `stale=true` until the newly selected board's own
next message arrives — consistent with the standing "never render stale data as
live" invariant — rather than continuing to show the previous board's last
values under a new label.

## `twin3d-kit.js`

Added at `twin/lib/twin3d-kit.js`. The merged twin was refactored to consume it
(`Twin3D.addLighting`, `Twin3D.createOrbitNav`) rather than keep the duplicate
inline copy — the nav construction moved from top-level script scope into
`initThree()`, since the kit captures `camera` by reference at construction
time and `cam3d` doesn't exist until that function runs.

## Verification

`fleet-manager/verify_physics.py` gained checks for all four corrections plus
the multi-feeder picker (board discovery, per-board filtering, forced-stale on
switch, `cmd/` exclusion). The physics-constant checks were reworked to match
this file's inline-literal style (`7250*(1 - 0.015*load)`) rather than the
named-constant style `mock_fleet.py` uses — different files, same firmware,
checked against its own idiom rather than forcing one style. All 55 checks
pass. The demo GIF was recaptured against the new visual design — the previous
one was for a UI that no longer exists in this repo.

## Consequence

Two independent builds of "the same twin," working from the same firmware,
arrived at two different wrong answers for frequency coupling — once corrected
in the docs (ADR-0002), once again here, independently, in code. That's not a
coincidence worth dismissing: it suggests the *reference material* this project
draws from carries the error more durably than any single artifact built from
it. Worth remembering the next time a new build starts from "what the project
already believes" rather than from the firmware directly.
