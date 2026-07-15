# ADR-0004: IPv6 global-unicast exposure vs. the no-internet-route invariant

**Status:** Open · **Date:** 2026-06

## Context

The lab's stated invariant (WRAITH §2.1, and the twin project's standing rules)
is that OT devices have **no route to the internet**. During a routine review of
the router's DHCP/DNS table, several lab devices were found holding **IPv6
global-unicast addresses** from the ISP's delegated prefix
(`2600:4040:2b45:5f00::/64`, Verizon). IPv6 was auto-configured; the planned
VLAN segmentation (Loop 4, MikroTik + OPNsense) is IPv4-only in its current
design and would **not** contain these addresses.

This is a documented invariant violation. It was caught by inspection, before
any exposure was exploited — but it is real.

## Decision

Record it openly as an **open** item rather than quietly fixing and forgetting.
Before any new inbound network path is added (remote twin access, etc.), the
IPv6 posture must be resolved:

* disable IPv6 on OT-segment interfaces, **or**
* firewall the delegated prefix at the OPNsense boundary, **and**
* verify no OT device answers on a global-unicast v6 address.

Every new network path in this repo is designed IPv4-only and behind the future
VLAN boundary — never as a bridged exception.

## Consequence

The gap is visible in the portfolio rather than hidden. Status stays **Open**
until Loop 4 lands and the v6 path is verified closed. This is the strongest
single maturity signal in the project: an invariant, a mechanism, and an honest
account of where the mechanism doesn't yet hold.
