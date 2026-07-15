# Unified Namespace (UNS)

Where the lab sits relative to a Unified Namespace, and what the target looks
like. The honest read: the stack is **UNS-adjacent** (MQTT-centric, single
broker, hierarchical topics, stateful lifecycle) but is **not a UNS** today.
Moving to a true UNS is a wire-level change (semantic namespace + self-describing
payload + report-by-exception), so it is a V2 goal, not built in V1.

> **Corrected against firmware.** An earlier draft described the lab's namespace
> as flat and its lifecycle semantics as absent. Both were wrong — read from
> stale reference docs rather than `universal_field.ino`. The lab is closer to a
> UNS than that draft claimed. See [ADR-0009](../adr/0009-parallel-repo-drift.md).

## What a UNS actually requires

A UNS is a single, structured, self-describing source of truth for all
operational data, typically on MQTT, usually with these properties:

- **Hierarchical, semantic namespace** (commonly ISA-95:
  Enterprise / Site / Area / Line / Cell / device / metric) — a consumer can
  understand a topic from its path alone.
- **Structured, self-describing payloads** — not a bare scalar.
- **Report by exception** — publish on change, retained/stateful, so a new
  subscriber can learn current state immediately.
- Often **Sparkplug B**, which standardizes the topic namespace, payload
  encoding, and birth/death lifecycle (NBIRTH/NDEATH/DBIRTH/DDEATH/DDATA).

## Current state (V1) — UNS-adjacent, not UNS

| Property | UNS target | V1 reality (verified against firmware) |
|---|---|---|
| Namespace | ISA-95 semantic hierarchy | **Two-level, role-rooted**: `grid/<board_short>/<metric>` — e.g. `grid/4d2238/voltage_a`. Not semantic, but genuinely hierarchical, and the board segment is a stable identity — not flat |
| Payload | Structured, self-describing | Bare `{"value": <float>, "device": "grid-substation-<tail>"}`. Carries device identity but no units, type, or quality |
| Delivery | Report by exception, stateful | **Mixed**: data tags publish on a fixed 2 s interval, unretained. Status **is** retained |
| Lifecycle | Birth/death certificates | **Present in primitive form**: retained birth (`"online"`) on connect + LWT death (`"offline"`) on ungraceful drop, at `grid/<short>/status`. This is NBIRTH/NDEATH in spirit — just not Sparkplug-encoded |
| Identity | Stable per-node id | **Present**: MAC-derived `board_short`, persisted, no per-board config |
| Encoding | Sparkplug B (typical) | Ad-hoc JSON |

The honest read is that three of the six properties are already partly there.
The real distance to a UNS is **semantic naming and payload self-description**,
not lifecycle or identity.

## Target namespace (proposed for V2)

ISA-95 mapping for this lab:

```
Catalyst / Homelab / GridSubstation / Feeder01 / <device> / <metric>
enterprise  site      area             line       edge node   tag
```

Under Sparkplug B, that surfaces on the standardized topic form:

```
spBv1.0/<group_id>/<message_type>/<edge_node_id>/<device_id>
        │           │              │              │
        │           │              │              └ e.g. grid-substation-4d2238
        │           │              └ e.g. GridEdge-01
        │           └ NBIRTH | NDEATH | DBIRTH | DDEATH | DDATA
        └ e.g. Catalyst-Homelab-GridSubstation
```

The lab is well-positioned: the Cirrus Link MQTT modules on the Ignition box
already speak Sparkplug B; MAC-derived board identity gives every edge node a
stable `edge_node_id` for free; and the existing retained-birth/LWT pattern maps
directly onto NBIRTH/NDEATH.

## The reconciliation (UNS vs. Zero Trust / 62443)

A UNS centralizes; Zero Trust and 62443 conduits isolate. The resolution is to
treat the **broker as a policy enforcement point**: one logical namespace, but
with per-topic authorization, per-device identity (Sparkplug edge-node identity
bound to a client cert), and zone-segmented broker access. That yields the single
source of truth *and* the zone/conduit boundaries simultaneously — see
[`README.md`](README.md) and the [62443 doc](iec-62443-zones-and-conduits.md).

## Why this is V2, not V1

Adopting a UNS changes the payload and topic structure on the wire, which touches
firmware, the bridge, the dashboard, the fleet manager, and the twin — exactly
the telemetry already validated on hardware for grid. Per the
one-thing-validated-before-the-next principle, this is sequenced as a deliberate
rework rather than folded into the V1 ship.
