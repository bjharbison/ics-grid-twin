# Architecture Decision Records

Short records of decisions that shaped this project, kept because the *reasoning*
is the portfolio signal — not the feature. Several of these document failures
caught before release. In an OT security context, a self-caught invariant
violation says more about judgment than any working demo does.

| ADR | Title | Status |
|----|-------|--------|
| [0001](0001-universal-firmware-mac-identity.md) | One universal binary, MAC-derived identity | Accepted |
| [0002](0002-firmware-is-ground-truth.md) | Firmware is ground truth; docs deferred to it | Accepted |
| [0003](0003-command-topic-scheme.md) | Canonical `cmd/<short>/#` scheme; drift caught pre-release | Accepted |
| [0004](0004-ipv6-exposure.md) | IPv6 global-unicast exposure vs. the no-internet-route invariant | Open |
| [0005](0005-credential-hygiene.md) | Credentials out of the repo; rotate what leaked | Accepted |
| [0006](0006-influx-tagging.md) | `board_id`/`device` as separate Influx tags | Accepted |
| [0007](0007-attack-tooling-scope.md) | Offensive tooling out of V1 by design | Accepted |
| [0008](0008-paho-api-compat.md) | paho-mqtt 1.x/2.x compat via a client factory | Accepted |
| [0009](0009-parallel-repo-drift.md) | Parallel repo diverged from firmware; harvest ideas, not code | Accepted |
