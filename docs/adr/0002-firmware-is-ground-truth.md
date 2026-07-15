# ADR-0002: Firmware is ground truth; documentation defers to it

**Status:** Accepted · **Date:** 2026-07-15

## Context

The lab accumulated several reference documents over months — a master homelab
doc, a digital-twin port, a fleet integration guide. When the validated
`universal_field.ino` (FW 1.0.0-grid) was read line by line to build V1, it
**contradicted the reference docs in six places.** The docs had drifted from the
code; the code is what runs on the boards.

## Decision

Where any document disagrees with flashed firmware, **firmware wins.** The twin
physics is a line-for-line port of `updatePhysics()`; the dashboard, fleet
manager, and schema all cite firmware behaviour, not the older specs. Each
correction is recorded below so the drift is visible rather than silently
resolved.

## The six corrections

1. **Tag names have no `_phase_` infix.** Firmware publishes `voltage_a/b/c`
   and `current_a/b/c`. Docs said `voltage_phase_a`. — twin, dashboard, schema
   all use the firmware names.

2. **breaker_status polarity: `1 = closed` (normal), `0 = open`.** Several docs
   asserted `0 = closed, 1 = open`. Firmware `publishTag("breaker_status",
   breakerClosed ? 1 : 0)` is unambiguous. Getting this backwards would invert
   the entire attack demo. — everything now keys off `>= 0.5 == closed`.

3. **Two undocumented tags: `power_factor`, `real_power_kw`.** The canonical set
   is 11 tags, not the 6–9 some docs implied. `real_power_kw` is computed
   in-firmware from `V·I·PF` and is a useful cross-check against a twin's own
   derived state.

4. **Frequency is NOT load-coupled.** Docs claimed frequency "dips under load."
   Firmware makes it a bounded random walk pulled toward 60.00 Hz, independent
   of load. The dashboard and twin annotate this rather than fake a coupling
   that isn't there.

5. **Transformer 80 °C red band is unreachable from load alone.** Firmware
   target is `45 + 30·load`, ceiling ~74.7 °C at max load. The 80 °C threshold
   is retained as an alarm limit but flagged: reaching it requires injection,
   not organic load. Honest thresholds beat dramatic ones.

6. **Status topic is a bare string, not JSON.** `grid/<short>/status` publishes
   `"online"`/`"offline"` (retained), while every data tag publishes
   `{"value":...}`. The bridge and fleet manager special-case it; parsing it as
   JSON would spam errors on every reconnect.

## Consequence

The twin is validated against ground truth, not a plausible guess. Anyone
reading the code can trace each value back to a firmware line. The stale
reference docs stay in the project as history, with this ADR as the correction
layer.
