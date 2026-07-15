# ADR-0009: A parallel repo diverged from firmware; harvest the ideas, not the code

**Status:** Accepted · **Date:** 2026-07-15

## Context

A second repository (`ics-ot-homelab`) was built for the same lab, in parallel,
in a different working session. When the two were compared before release, they
disagreed on nearly every wire-level fact:

| | parallel repo | flashed firmware (ground truth) |
|---|---|---|
| `breaker_status` | 0 = CLOSED, 1 = OPEN | **1 = CLOSED, 0 = OPEN** |
| tag names | `voltage_phase_a` | `voltage_a` |
| topic | `grid/<tag>` (flat) | `grid/<short>/<tag>` |
| breaker open | voltage → 0, freq → 0 (full de-energization) | **voltage HOLDS**, current collapses |
| V nominal | 7200 | 7250 |
| frequency | coupled to load | not coupled |
| payload | includes `timestamp` | no timestamp |
| device id | `grid-substation-01` | `grid-substation-<mac_tail>` |

The parallel repo was **internally consistent** — its simulator, bridge, Grafana
mappings, and safety doc all agreed with each other. They simply all agreed with
the project's *stale reference documentation* rather than with the firmware.

The most serious consequence was in its safety document, which defined the
flagship demo as *"forcing `grid/breaker_status = 1` and watching the coupled
model cascade de-energization."* That is wrong twice: on the real boards `= 1`
**closes** the breaker (the normal state), and cascade de-energization is the
signature of a **fault**, not a commanded trip. The detection value of the entire
demo rests on the opposite claim — current collapses while voltage holds. Shipped
as-is, the flagship artifact would have argued against its own thesis, in front
of exactly the audience most likely to notice.

## Decision

**Retire the parallel repo rather than merge it.** Harvest the ideas that filled
real gaps, and re-implement each against firmware:

1. **A no-hardware fleet simulator** — a genuine gap. This repo's no-hardware
   path covered only the browser twin; the *pipeline* (bridge → InfluxDB →
   Grafana) still required real boards. Re-implemented from firmware as
   `scripts/mock_fleet.py`, six feeders, faithful physics, correct polarity.
2. **CI** — a genuine gap. Adapted as `.github/workflows/ci.yml`, keeping the
   good parts (full-history secret scan, assert-no-secret-files-tracked) and
   adding the invariant suite as a build gate.
3. **Framework docs** (IEC 62443, NIST SP 800-82r3, Zero Trust, UNS) — genuinely
   strong and absent here. Ported *after audit*: the UNS doc had inherited the
   same errors and, ironically, **understated** the lab, describing its namespace
   as flat and its lifecycle semantics as absent when the firmware has a
   two-level hierarchy, stable MAC-derived identity, and retained birth/LWT.

## Consequence

The harvested simulator is now the most heavily guarded file in the repo.
`verify_physics.py` asserts, and CI enforces, that it uses firmware tag names,
per-board topics, correct breaker polarity, no timestamp field, firmware physics
constants, and — specifically — that **voltage sags against `cur_load` while
current is driven by `ld`**, which is the one line that makes a trip hold voltage
instead of blacking out.

The general lesson is the one ADR-0002 already recorded, now with a second data
point: *two artifacts built from the same docs will agree with each other and be
wrong together.* Internal consistency is not evidence of correctness. Only the
device is evidence. When a drift is found, the fix is not a correction — it is an
assertion that fails the build next time.
