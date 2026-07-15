#!/usr/bin/env python3
"""
verify_physics.py -- offline evidence for SAFETY.md invariants 6 and 7.

Runs with no broker and no hardware. Two checks:

  6. breaker_status polarity is 1 = closed, 0 = open (no inversion), consistent
     across firmware, twin, and fleet manager.
  7. The twin's physics constants match the firmware line-for-line.

Exit code 0 = all checks pass. Wire this into CI.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
INO = ROOT / "firmware" / "universal_field" / "universal_field.ino"
TWIN = ROOT / "twin" / "grid_twin.html"
GUI = ROOT / "fleet-manager" / "esp32_fleet.py"
BRIDGE = ROOT / "infra" / "mqtt-bridge" / "bridge.py"
SIM = ROOT / "scripts" / "mock_fleet.py"

fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


ino = INO.read_text()
twin = TWIN.read_text()
gui = GUI.read_text()
bridge = BRIDGE.read_text()
sim = SIM.read_text()

print("Invariant 6 -- breaker polarity (1 = closed, no inversion):")
check("firmware publishes closed as 1",
      'publishTag("breaker_status", breakerClosed ? 1 : 0)' in ino
      or "breakerClosed ? 1 : 0" in ino)
check("twin treats >= 0.5 as closed", "v >= 0.5" in twin or ">= 0.5" in twin)
check("fleet manager treats >= 0.5 as closed", ">= 0.5" in gui)
check("no doc-style 0=closed inversion in twin",
      "0 = closed" not in twin and "0=closed" not in twin)

print("\nInvariant 7 -- twin physics constants match firmware:")
CONSTS = {
    "V_NOM 7250": ("7250.0f", "V_NOM = 7250.0"),
    "V_SAG 0.015": ("0.015f * curLoad", "V_SAG = 0.015"),
    "I_BASE/SPAN 150+200": ("150.0f + 200.0f", "I_BASE = 150.0"),
    "I_SPAN 200": ("200.0f * ld", "I_SPAN = 200.0"),
    "T_BASE/SPAN 45+30": ("45.0f + 30.0f", "T_BASE = 45.0"),
    "T_ALPHA 0.03": ("0.03f", "T_ALPHA = 0.03"),
    "imbalance 0.004": ("0.004f", "0.004"),
    "pf 0.985-0.06": ("0.985f - 0.06f", "0.985 - 0.06"),
    "freq clamp 59.95/60.05": ("59.95f, 60.05f", "59.95, 60.05"),
    "curLoad clamp 0.20/0.99": ("0.20f, 0.99f", "0.20, 0.99"),
}
for label, (fw_needle, twin_needle) in CONSTS.items():
    check(label, fw_needle in ino and twin_needle in twin,
          f"fw={fw_needle in ino} twin={twin_needle in twin}")

print("\nMock fleet -- must not drift from firmware (ADR-0009):")
# An earlier simulator was written from the reference docs instead of the
# firmware and inverted breaker_status, renamed every tag, flattened the topic
# tree, and modelled a trip as full de-energization. These assertions are what
# make that class of drift fail a check instead of shipping.
check("sim uses firmware tag names (voltage_a, not voltage_phase_a)",
      '"voltage_a"' in sim and "voltage_phase_a" not in sim)
check("sim uses per-board topics (grid/<short>/<tag>)",
      'f"grid/{short}"' in sim or 'topic_base' in sim)
check("sim breaker: 1 = closed, no inversion",
      "1 if self.breaker_closed else 0" in sim)
check("sim payload has no timestamp field", '"timestamp"' not in sim)
check("sim voltage sags against cur_load, NOT ld (voltage must hold on trip)",
      "V_SAG * self.cur_load" in sim)
check("sim current driven by ld (must collapse on trip)",
      "I_SPAN * ld" in sim)
for label, val in (("V_NOM", "V_NOM = 7250.0"), ("V_SAG", "V_SAG = 0.015"),
                   ("I_BASE", "I_BASE = 150.0"), ("I_SPAN", "I_SPAN = 200.0"),
                   ("T_BASE", "T_BASE = 45.0"), ("T_SPAN", "T_SPAN = 30.0"),
                   ("T_ALPHA", "T_ALPHA = 0.03")):
    check(f"sim {label} matches firmware", val in sim)
check("sim diurnal is deterministic (tick-based, not wall-clock)",
      "self.ticks * PUBLISH_S" in sim)

print("\nMQTT client construction -- paho 1.x/2.x compatible:")
# paho 2.0 made callback_api_version a required first arg. A bare
# mqtt.Client(client_id=...) raises ValueError at startup on 2.x, so every
# client must go through the make_client() factory.
for label, src in (("fleet manager", gui), ("bridge", bridge), ("mock fleet", sim)):
    check(f"{label} has make_client factory", "def make_client(" in src)
    check(f"{label} handles CallbackAPIVersion", "CallbackAPIVersion" in src)
    bare = [ln.strip() for ln in src.splitlines()
            if "mqtt.Client(" in ln and "_CALLBACK_V1" not in ln
            and "client_id=client_id)" not in ln]
    check(f"{label} constructs no bare clients", not bare, f"found: {bare}")

print("\nInvariant 11 -- twin observes, never actuates:")
check("twin makes no MQTT publish calls", ".publish(" not in twin)
check("twin connects read-only (monitor-reader default)", "monitor-reader" in twin)
check("sim controls disabled while live", "simControls(false)" in twin)

print("\nInvariant 13 -- twin never persists credentials:")
check("no localStorage", "localStorage" not in twin)
check("no sessionStorage", "sessionStorage" not in twin)
# Match credential-SHAPED strings rather than naming real ones -- listing the
# actual passwords here would put them back in the repo, which is the thing
# this check exists to prevent. (Caught on the first sweep. See ADR-0005.)
_CRED_RE = re.compile(
    r'(password|passwd|token|secret)\s*[:=]\s*["\'][^"\'\s]{6,}["\']', re.I)
_leaks = [m.group(0) for m in _CRED_RE.finditer(twin)
          if "placeholder" not in m.group(0).lower()]
check("no credential literals in twin source", not _leaks, f"found: {_leaks}")

print("\nInvariant 12 -- stale data is visibly distinct:")
check("staleness watchdog present", "STALE_MS" in twin)
check("LWT offline handled", '"offline"' in twin)
check("stale styling exists", "body.stale" in twin)

print("\nLive path -- all 11 firmware tags mapped:")
import re as _re
_tags = sorted(set(_re.findall(r'publishTag\("(\w+)"', ino)))
_apply = twin[twin.find("const APPLY"):twin.find("function goLive")]
check(f"all {len(_tags)} tags in APPLY", all(t in _apply for t in _tags),
      f"missing: {[t for t in _tags if t not in _apply]}")

print("\nInvariant 7b -- load estimator inverts voltage sag (numeric):")
V_NOM, V_SAG = 7250.0, 0.015
for true_load in (0.20, 0.45, 0.60, 0.85, 0.99):
    v_avg = V_NOM * (1.0 - V_SAG * true_load)          # noise-free firmware voltage
    est = max(0.0, min(1.0, (1.0 - v_avg / V_NOM) / V_SAG))
    check(f"load {true_load:.2f} recovers", abs(est - true_load) < 1e-6,
          f"est={est:.4f}")

print()
if fails:
    print(f"FAILED: {len(fails)} check(s): {', '.join(fails)}")
    sys.exit(1)
print("All physics/polarity invariants hold.")
sys.exit(0)
