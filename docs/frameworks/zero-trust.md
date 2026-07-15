# Zero Trust — NIST SP 800-207 applied to OT

Mapping the lab against the seven Zero Trust tenets from NIST SP 800-207. The lab
has real ZT *primitives* — deny-by-default authorization, least-privilege
accounts, read-only data consumers — but two core tenets (secure-all-comms and
per-asset identity) are gaps in V1, and they are the same gaps that hold the
62443 Security Level down. Flagged here, deferred to the V2 rework.

## OT caveat up front

Zero Trust was written for enterprise IT. Applying it to OT requires judgment,
not literal transcription: OT prioritizes **availability and safety over
confidentiality**, devices are fragile and long-lived, and "authenticate every
session dynamically" can be infeasible on a constrained field device. The goal
is to honour ZT *intent* — never trust the network, enforce identity and least
privilege at policy enforcement points — without pretending an ESP32 can do
enterprise IdP flows. Where a tenet doesn't fit cleanly, that is stated rather
than forced.

## Tenet mapping

| # | SP 800-207 tenet | Lab status | Detail |
|---|---|---|---|
| 1 | All data sources & services are resources | **Implemented** | Every board, broker, historian, and dashboard is a discrete resource with its own access rules |
| 2 | Secure all communication regardless of network location | **Gap** | MQTT is plaintext on :1883 (and :9001 WS); no mTLS. Flat subnet today. The headline V1 gap |
| 3 | Per-session access to individual resources | **Partial** | Pub/sub isn't session-oriented, but access is per-account and per-topic; no dynamic session grants |
| 4 | Access via dynamic policy (identity, asset state, attributes) | **Partial** | Policy (ACL) is static; no posture/attribute signals feed authz yet |
| 5 | Monitor & measure integrity/posture of all assets | **Partial** | Grafana thresholds + staleness/LWT tracking in-repo; Zeek passive capture and Wazuh SIEM are lab/planned |
| 6 | Authn/authz dynamic & strictly enforced before access | **Partial** | Deny-by-default ACL strictly enforced; but static and per-shared-account, not dynamic/per-device |
| 7 | Collect telemetry to improve posture continuously | **Partial** | Historian closes the loop; the blue-team view (dashboard + twin) runs alongside the demo, which is the point of building it this way |

## The two load-bearing gaps

**Per-asset identity (tenets 4, 6).** All six boards authenticate as a single
shared `esp32-field` credential. That is a ZT anti-pattern: if one field
credential leaks, every board is impersonatable. The fix is native to this lab —
board identity is already MAC-derived and persisted, so issuing per-device
credentials or X.509 client certs (CN = `board_short`) is a provisioning change,
not a redesign.

**Secure all communication (tenet 2).** Plaintext MQTT means no transport
confidentiality or integrity. mTLS on :8883 with a lab CA closes this and
simultaneously delivers per-device identity (the client cert *is* the identity),
which is why V2 treats identity and transport as one workstream.

## A third gap worth naming: the broker trusts, it does not verify

The lab's own history makes the ZT case better than any diagram. A supervisory
command published to `cmd/<short>/breaker` returned success while the broker
silently declined to deliver it, because the ACL lacked a read rule
([ADR-0003](../adr/0003-command-topic-scheme.md)). Authorization was working
exactly as designed and the *publisher had no idea*. Under ZT terms: there is no
feedback path from the policy enforcement point back to the requester. The fleet
manager compensates by telling the operator that broker-acceptance is not
delivery and the effect must be confirmed in telemetry — a mitigation, not a fix.

## Microsegmentation vs. macrosegmentation

The planned VLAN work (Loop 4: MikroTik + OPNsense) is **macro**-segmentation —
zone-level isolation. True **micro**-segmentation is per-asset policy enforced at
the OPNsense boundary and, for the message bus, per-topic + per-device authz at
the broker. V1 documents the target. Note that the IPv6 finding
([ADR-0004](../adr/0004-ipv6-exposure.md)) currently undercuts even the macro
plan: global-unicast v6 addresses would route around an IPv4-only VLAN.

## What V1 legitimately claims

- Deny-by-default authorization at the broker (tenet 6, intent).
- Least-privilege, purpose-scoped accounts; consumers are read-only (tenets 1, 6).
- Separation of read and write capability into distinct credentials and distinct
  clients, with write off by default (tenet 6).
- Continuous monitoring foundation via the historian (tenets 5, 7).

## What V1 does *not* claim

- Encrypted/authenticated transport (tenet 2) — **gap, V2**.
- Per-device identity and dynamic policy (tenets 4, 6) — **gap, V2**.
- Enforced network segmentation (tenet 3 boundary) — **planned, Loop 4, blocked
  on the IPv6 finding**.
