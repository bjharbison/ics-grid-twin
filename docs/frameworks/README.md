# Security & architecture frameworks

This layer maps the lab against the frameworks an OT security reviewer will look
for. It is **framing and documentation only** — V1 does not change any field
device, payload, or transport to satisfy a framework. Where a framework requires
a wire-level change to be genuinely met (per-device identity, mTLS, Sparkplug B),
that gap is stated honestly and deferred to V2.

That honesty is deliberate. In OT, a documented *target vs. achieved* gap is a
stronger signal than a checklist of green boxes — it shows the invariants are
real and being measured.

## Scope: the lab vs. this repo

These docs describe the **whole homelab**, which is wider than this repository.
This repo ships the grid substation slice: firmware, broker/historian stack,
fleet manager, dashboard, and twin. Where a control below lives elsewhere in the
lab (Zeek, Ignition, OPNsense, or the separately-governed WRAITH harness), it is
marked as such rather than implied to be in this tree.

## The four lenses

| Doc | Lens | V1 status |
|---|---|---|
| [`iec-62443-zones-and-conduits.md`](iec-62443-zones-and-conduits.md) | Zones, conduits, target vs. achieved Security Level | Documented; SL-A honestly below SL-T |
| [`zero-trust.md`](zero-trust.md) | NIST SP 800-207 tenets applied to OT | Primitives in place; identity + transport gaps flagged |
| [`nist-sp-800-82r3.md`](nist-sp-800-82r3.md) | OT overlay → SP 800-53 Rev 5 control mapping | Control map: implemented / partial / planned |
| [`unified-namespace.md`](unified-namespace.md) | UNS / ISA-95 namespace, Sparkplug B path | UNS-adjacent, not a UNS; target defined for V2 |

## The tension worth naming

These four do not all pull the same direction.

- **UNS wants centralization:** one logical namespace, everything is a broker
  client, single source of truth.
- **Zero Trust, microsegmentation, and 62443 conduits want isolation:**
  per-asset identity, least-privilege data flows, hard boundaries between zones.

They are reconciled by making the **broker a policy enforcement point** rather
than a flat message bus: a single namespace, but with per-topic authorization,
per-device identity, and zone-segmented broker access. You get the one namespace
*and* the zone/conduit boundaries at the same time. The wire-level mechanics that
make this true (Sparkplug B, per-device certs, mTLS) are V2 work.

## A note on provenance

An earlier draft of these docs was written against the project's reference
documentation rather than the flashed firmware, and inherited its errors — most
consequentially, it described the lab's namespace as flat and its lifecycle
semantics as absent, when the firmware has neither problem. Every factual claim
here has since been checked against `universal_field.ino`. See
[ADR-0009](../adr/0009-parallel-repo-drift.md) and
[ADR-0002](../adr/0002-firmware-is-ground-truth.md).

## Scope note

The offensive/assessment harness (WRAITH) is governed separately and its current
build explicitly excludes the offensive engine. Nothing in this layer changes
that, and this repo ships no attack tooling ([ADR-0007](../adr/0007-attack-tooling-scope.md)).
