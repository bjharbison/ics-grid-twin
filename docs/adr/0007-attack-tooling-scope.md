# ADR-0007: Offensive tooling out of V1 by design

**Status:** Accepted · **Date:** 2026-07-15

## Context

The lab's demo scenarios reference real attack TTPs (Industroyer/CRASHOVERRIDE
breaker manipulation; the Oldsmar water-treatment setpoint incident). It is
tempting to ship the offensive side — Modbus write scripts from Kali, etc.

## Decision

V1 ships the **detection and visualization** side only. Attack scenarios are
*described* (in docs and as the twin's simulated "Industroyer scenario"), not
*weaponized*. No Modbus-write exploit scripts, no attack automation, in this
repo. This mirrors WRAITH, which scopes its offensive engine out of the
governed platform by design.

## Consequence

The repo demonstrates understanding of the attack (the twin reproduces the
signature: current/power collapse with voltage holding) without shipping a
turnkey ICS attack tool. For the target audience — OT defenders and safety-
minded reviewers — restraint here is the signal, not a gap. Offensive work,
if ever added, lives in a separate change-controlled context. Marked
**aspirational for V2+** in the README.
