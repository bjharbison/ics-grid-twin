# NIST SP 800-82 Rev 3 — OT security control mapping

NIST SP 800-82 Revision 3 (September 2023) broadened the guide's scope from ICS
to **Operational Technology** generally, and functions as an OT tailoring/overlay
on the SP 800-53 Rev 5 control catalog. This maps the lab's controls to the
relevant 800-53 families, marked implemented / partial / planned. It is a mapping
exercise — no control is newly built here.

## OT overlay considerations (why this isn't a straight 800-53 copy)

Rev 3 stresses that OT tailors IT controls for a different priority order:
**safety and availability first**, constrained/fragile/long-lived devices,
non-disruptive control selection, and real-world constraints on patching,
authentication, and scanning. The mapping reflects that — reflash-based recovery
is treated as a first-class control, and aggressive scanning is deliberately
bounded.

## Control mapping

| Family | Control(s) | Lab implementation | Status |
|---|---|---|---|
| **AC** Access Control | AC-3 Access Enforcement | Mosquitto deny-by-default ACL | ✅ Implemented |
| | AC-4 Information Flow Enforcement | Conduit model; ACL scopes field→ops flow; VLAN planned | 🟡 Partial |
| | AC-6 Least Privilege | Three purpose-scoped accounts; consumers read-only; ACL grants only live roles, not reserved ones | ✅ Implemented |
| **IA** Identification & Authentication | IA-2 Identification & Authentication | Broker requires auth; **shared** field credential across all boards | 🟡 Partial |
| | IA-5 Authenticator Management | Secrets in Vaultwarden; templated, never committed; gitleaks pre-commit + CI; rotation-on-exposure is a release gate | 🟡 Partial (no per-device authenticators) |
| **AU** Audit & Accountability | AU-2 / AU-3 / AU-12 | Bridge + broker logs; fleet manager event log. WRAITH's immutable audit hook is a separate project | 🟡 Partial |
| **SC** System & Communications Protection | SC-7 Boundary Protection | IT/OT DMZ (broker zone); OPNsense + VLAN planned; **IPv6 exposure open** | 🟡 Partial — [ADR-0004](../adr/0004-ipv6-exposure.md) |
| | SC-8 Transmission Confidentiality/Integrity | **Plaintext MQTT** — not met | 🔴 Planned (mTLS, V2) |
| | SC-5 DoS Protection | Not implemented at the broker. (WRAITH L0 rate/concurrency caps protect devices *from the harness*, not from this conduit) | 🔴 Planned |
| **CM** Configuration Management | CM-2 / CM-6 Baseline & Settings | Versioned firmware; docker-compose + Grafana provisioning as code; physics constants asserted against firmware in CI | ✅ Implemented |
| | CM-7 Least Functionality | Single-purpose containers; field devices publish-only; twin subscribe-only | ✅ Implemented |
| **SI** System & Information Integrity | SI-4 System Monitoring | Grafana thresholds; staleness/LWT tracking. Zeek passive capture is lab; Wazuh planned | 🟡 Partial |
| **RA** Risk Assessment | RA-5 Vulnerability Monitoring | Secret scanning (gitleaks) in pre-commit **and CI, over full history**; broader scanning bounded for OT fragility | 🟡 Partial |
| **CP** Contingency Planning | CP-9 / CP-10 Backup & Recovery | Lab snapshots; versioned, OTA-reflashable firmware for deterministic recovery | ✅ Implemented |
| **CA** Assessment, Authorization & Monitoring | CA-7 Continuous Monitoring | Historian + dashboard as the monitoring baseline; planned SIEM | 🟡 Partial |

## Headline gap

**SC-8 (transmission confidentiality/integrity)** is the single red item and the
root of several partials: plaintext MQTT means no per-device authenticator on the
wire (IA-2/IA-5) and no message integrity. The V2 mTLS + per-device identity
rework moves SC-8 to implemented and upgrades IA-2/IA-5 in the same change.

## An OT-specific note on CM-2

Configuration baselining in OT usually means firmware versions and device
settings. This lab extends it somewhere less obvious: the *model* is baselined
against the device. The twin, the mock fleet, and the fleet manager all assert
their physics constants and tag semantics against `universal_field.ino` in CI
([ADR-0002](../adr/0002-firmware-is-ground-truth.md),
[ADR-0009](../adr/0009-parallel-repo-drift.md)). Documentation drifting from
device behaviour is an OT failure mode with real consequences — an operator
trusting a display that no longer reflects the plant — and it is treated here as
a configuration-management problem, because that is what it is.

## Honest framing

Most families sit at partial precisely because this is a lab being built
one-validated-step-at-a-time, not a production system claiming an authorization
boundary. The value of this table is the *delta*: which OT-tailored controls
exist, which are scaffolded, and which are explicitly on the roadmap — tied to
concrete build loops rather than aspiration.
