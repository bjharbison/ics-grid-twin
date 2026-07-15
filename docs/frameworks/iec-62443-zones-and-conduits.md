# IEC 62443 — Zones & Conduits

Framing the lab under the IEC 62443 zone/conduit model (62443-3-2 for the
partitioning, 62443-3-3 for system requirements and Security Levels). This is a
documentation exercise — no control here is newly built to hit a Security Level;
the achieved levels are reported honestly against the target.

## Model recap

- **Zone** — a grouping of assets that share security requirements.
- **Conduit** — the logical grouping of communication channels between zones,
  governed as a unit.
- **Security Level (SL)** — measured against seven Foundational Requirements:
  FR1 Identification & Authentication Control · FR2 Use Control ·
  FR3 System Integrity · FR4 Data Confidentiality · FR5 Restricted Data Flow ·
  FR6 Timely Response to Events · FR7 Resource Availability.
- **SL-T / SL-A / SL-C** — Target / Achieved / Capability. SL-1 resists casual or
  coincidental violation; SL-2 resists intentional violation by simple means, low
  resources, generic skills, low motivation; SL-3 adds sophistication and
  OT-specific skills; SL-4 extended resources and high motivation.

## Zones

| Zone | Purdue | Assets | In this repo? |
|---|---|---|---|
| **Z0 — Field / Process** | L0–L1 | 6× ESP32 field devices (grid role live) | ✅ firmware, mock fleet |
| **Z1 — Broker / IT-OT DMZ** | L3.5 | Mosquitto broker, mqtt-bridge | ✅ `infra/` |
| **Z2 — Operations / Historian** | L3 | InfluxDB, Grafana, twin; Ignition (lab) | ✅ partly — Ignition is lab-only |
| **Z3 — Enterprise** | L4 | Dev laptop, Arduino IDE, fleet manager | ✅ `fleet-manager/` |
| **Z4 — Security / Management** | cross-cutting | Zeek, Wazuh (planned), Vaultwarden, WRAITH control plane | ❌ lab / separate project |
| **Z5 — Offensive (test only)** | isolated | Kali | ❌ **not shipped** — [ADR-0007](../adr/0007-attack-tooling-scope.md) |

## Conduits

| Conduit | From → To | Channel | Governing control (V1) | FRs exercised |
|---|---|---|---|---|
| **C1 — Field telemetry** | Z0 → Z1 | MQTT publish `grid/<short>/#`, :1883 | `esp32-field` publish-only, deny-by-default ACL | FR1, FR2, FR5 |
| **C2 — Historian ingest** | Z1 → Z2 | MQTT sub (bridge) → InfluxDB write | `monitor-reader` read-only; bridge cannot write devices | FR2, FR5 |
| **C3 — Visualization** | Z2 → Z3 | Grafana HTTP :3000; twin over WS :9001 | Grafana auth; twin is subscribe-only, `monitor-reader` | FR1, FR2 |
| **C4 — Supervisory control** | Z3 → Z1 → Z0 | MQTT publish `cmd/<short>/<verb>` | `scada-server`, separate credential, off by default, confirm-on-use | FR1, FR2 |
| **C5 — Remote mgmt** | Z3/ext → Z1/Z2 | Tailscale | Identity-based overlay, no broad inbound | FR1, FR5 |

> The original draft of this table carried a sixth conduit for a Kali attack
> path. It is removed: this repo ships no offensive tooling, and the breaker-trip
> demo is exercised through C4 (a documented supervisory command against the
> operator's own simulated board) or the twin's simulator — not an exploit chain.

## Target vs. achieved Security Level (honest reporting)

Take conduit **C1 (field telemetry)** as the worked example — the most
security-relevant boundary in the lab.

| FR | SL-T (target) | SL-A (achieved V1) | Gap closing the delta |
|---|---|---|---|
| FR1 IAC | SL-2 (per-device identity) | **SL-1** — one shared `esp32-field` credential across all boards | Per-device creds or X.509 client certs (MAC-derived) → V2 |
| FR2 UC | SL-2 | **SL-2** — deny-by-default, publish-only, topic-scoped ACL | Met |
| FR3 SI | SL-2 | **SL-1** — no message integrity on the wire | Signed/authenticated transport (mTLS) → V2 |
| FR4 DC | SL-2 | **SL-0/1** — plaintext MQTT on :1883 | TLS on :8883 → V2 |
| FR5 RDF | SL-2 | **SL-1** — ACL restricts flow; no network segmentation yet, and IPv6 global-unicast bypasses the planned IPv4 VLAN | VLAN + OPNsense (Loop 4); close IPv6 first — [ADR-0004](../adr/0004-ipv6-exposure.md) |
| FR6 TRE | SL-2 | **SL-1** — Grafana thresholds; no alerting pipeline | Wazuh SIEM + alert routing (Loop 5/8) |
| FR7 RA | SL-2 | **SL-1/2** — versioned, OTA-reflashable firmware gives deterministic recovery; no rate limiting on the broker itself | Broker-side rate caps → V2 (WRAITH's L0 caps govern the harness, not this conduit) |

**Reading of C1:** *use control* is at target; *identity, integrity, and
confidentiality* are the honest gap, all closed by the same V2 wire-level rework
(per-device identity + mTLS). Stating this is the point — it shows the SL model
is being measured, not decorated.

## Conduit diagram

```
        Z3 Enterprise
       (dev laptop, fleet manager, browser)
              │  C3 (Grafana HTTP / twin WS)        C4 (cmd/<short>/<verb>,
              ▼                                          scada-server, off by default)
   ┌───────────────────────┐        Z4 Security / Mgmt        │
   │ Z2 Operations         │◄──────  (Zeek, Wazuh*,           │
   │ InfluxDB, Grafana,    │          Vaultwarden, WRAITH)    │
   │ twin, Ignition*       │                                  │
   └───────────▲───────────┘                                  │
               │  C2 (bridge: monitor-reader, read-only)      │
   ┌───────────┴──────────────────────────────────────────────▼┐
   │ Z1 Broker / IT-OT DMZ — Mosquitto + bridge                 │
   └───────────▲───────────────────────────────────────────────┘
               │  C1 (esp32-field, publish-only, ACL grid/#, :1883 plaintext ⚠)
   ┌───────────┴───────────┐
   │ Z0 Field / Process    │
   │ 6× ESP32 (grid live)  │
   └───────────────────────┘
        * lab, not shipped in this repo
```

## V2 hooks

The gaps above (FR1/FR3/FR4 on C1) are not fixed in V1. Closing them to SL-2 is
the subject of the V2 wire-level rework: per-device identity + mTLS + Sparkplug B,
landing together because the client certificate *is* the identity.
