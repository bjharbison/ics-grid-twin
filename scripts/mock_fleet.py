#!/usr/bin/env python3
"""
mock_fleet.py -- stand in for the whole six-board ESP32 fleet. NO HARDWARE.

Lets someone who has cloned this repo and owns zero ESP32s bring up the entire
pipeline and watch it work:

    docker compose up -d          # broker + bridge + influx + grafana
    python scripts/mock_fleet.py  # six feeders start publishing
    -> Grafana "ICS Grid Substation - Fleet" populates, both rows
    -> the fleet manager discovers six feeders and can trip their breakers
    -> the twin's "Connect to fleet" finds them

WHAT THIS IS
    A stand-in for a field device. It is NOT firmware, is not flashed to
    anything, and does not model a substation to engineering accuracy.

WHAT IT IS NOT
    A guess. `updatePhysics()` below is a line-for-line port of
    universal_field.ino (FW 1.0.0-grid) -- same constants, same coupling, same
    2 s interval, same wire format. If this file and the firmware ever disagree,
    the firmware is right and this is a bug. `verify_physics.py` asserts they
    match, so the disagreement fails a check rather than quietly shipping.

    That is not a hypothetical. An earlier simulator was written from the
    project's reference docs rather than the firmware, and inverted
    breaker_status, renamed every tag, flattened the topic tree, and modelled a
    breaker trip as full de-energization. See ADR-0009.

THE SIGNATURE THIS EXISTS TO REPRODUCE
    Opening a breaker collapses feeder CURRENT and REAL POWER while bus VOLTAGE
    HOLDS. That is Industroyer / 2016 Ukraine. It is NOT a blackout. Full
    de-energization is what a fault looks like; a commanded trip looks like this.

Credentials come from the environment (.env). Nothing is hardcoded.

Usage:
    pip install -r requirements.txt
    cp ../.env.example ../.env          # fill in MQTT_FIELD_PASSWORD
    python mock_fleet.py
    python mock_fleet.py --trip-after 60            # trip feeder 1 after 60 s
    python mock_fleet.py --trip-after 60 --trip-board 4d2238
    python mock_fleet.py --boards 2                 # fewer feeders
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import signal
import sys
import time

try:
    import paho.mqtt.client as mqtt
except ImportError:
    sys.exit("paho-mqtt is required:  pip install -r requirements.txt")


# paho 2.0 made callback_api_version a required first argument; the 1.x-style
# constructor raises ValueError at startup. Callbacks here are VERSION1-shaped.
# See ADR-0008.
try:
    _CALLBACK_V1 = mqtt.CallbackAPIVersion.VERSION1      # paho >= 2.0
except AttributeError:
    _CALLBACK_V1 = None                                  # paho 1.x


def make_client(client_id: str) -> "mqtt.Client":
    if _CALLBACK_V1 is not None:
        return mqtt.Client(_CALLBACK_V1, client_id=client_id)
    return mqtt.Client(client_id=client_id)


# ---------------------------------------------------------------------------
# Firmware constants -- universal_field.ino. Do not tune these independently.
# ---------------------------------------------------------------------------
PUBLISH_S = 2.0          # firmware PUBLISH_MS 2000
V_NOM = 7250.0           # voltage[i] = 7250 * (1 - 0.015*curLoad) * imbalance
V_SAG = 0.015
I_BASE = 150.0           # current[i] = (150 + 200*ld) * imbalance
I_SPAN = 200.0
T_BASE = 45.0            # target = 45 + 30*ld
T_SPAN = 30.0
T_ALPHA = 0.03           # xfmrTemp += (target - xfmrTemp) * 0.03
PF_BASE = 0.985          # pf = 0.985 - 0.06*ld
PF_SLOPE = 0.06
F_NOM = 60.00

# Synthetic MAC tails standing in for the fleet's MAC-derived identity. These
# are FAKE -- real boards derive theirs from the chip. `4d2238` matches the
# board used in the lab's validated breaker-trip test, so demos read familiar.
DEFAULT_BOARDS = ["4d2238", "3ca4f2", "a1b3c7", "7e2d91", "c40f16", "9b5e83"]

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_FIELD_USER", "esp32-field")
MQTT_PASS = os.environ.get("MQTT_FIELD_PASSWORD", "")


class Feeder:
    """
    One simulated board. Mirrors universal_field.ino state and physics exactly.

    Each feeder is its own MQTT client, like a real board: its own LWT on
    grid/<short>/status, its own cmd/<short>/# subscription. That fidelity is
    what lets the fleet manager and the twin exercise their real code paths --
    discovery, per-board commands, LWT offline -- with no hardware present.
    """

    def __init__(self, short: str):
        self.short = short
        self.device = f"grid-substation-{short}"
        self.topic_base = f"grid/{short}"

        # firmware deriveIdentity():
        #   seed = mac[3]<<16 | mac[4]<<8 | mac[5]   -- i.e. the MAC tail
        #   boardOffset = ((seed % 100)/100 - 0.5) * 0.10     -> +/-0.05
        #   randomSeed(seed)
        seed = int(short, 16)
        self.offset = ((seed % 100) / 100.0 - 0.5) * 0.10
        # Per-board RNG stream, seeded from identity -- mirrors randomSeed(seed)
        # and keeps every run reproducible. NOT Python's hash(): it is
        # randomized per process, which would make "deterministic per-board
        # offset" a lie.
        self.rng = random.Random(seed)

        # firmware initial state
        self.load_walk = 0.60
        self.cur_load = 0.60
        self.V = [0.0, 0.0, 0.0]
        self.I = [0.0, 0.0, 0.0]
        self.freq = 60.00
        self.pf = 0.97
        self.kw = 0.0
        self.temp = 55.0
        self.breaker_closed = True

        self.ticks = 0
        self.client: mqtt.Client | None = None

    # -- Arduino shims ------------------------------------------------------
    def _arnd(self, a: int, b: int) -> int:
        """Arduino random(a, b) -- integer, upper-exclusive."""
        return self.rng.randrange(a, b)

    @staticmethod
    def _constrain(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, v))

    # -- connectivity -------------------------------------------------------
    def connect(self) -> None:
        c = make_client(self.device)          # firmware uses deviceName as client id
        c.username_pw_set(MQTT_USER, MQTT_PASS)
        will = f"{self.topic_base}/status"
        # firmware: mqtt.connect(..., willTopic, 0, true, "offline")
        c.will_set(will, "offline", qos=0, retain=True)
        c.on_connect = self._on_connect
        c.on_message = self._on_message
        c.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
        c.loop_start()
        self.client = c

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc != 0:
            print(f"[{self.short}] connect failed rc={rc} ({mqtt.connack_string(rc)})")
            return
        # firmware: birth (retained), then subscribe to command topics
        client.publish(f"{self.topic_base}/status", "online", qos=0, retain=True)
        client.subscribe(f"cmd/{self.short}/#")
        client.subscribe("cmd/all/#")

    def _on_message(self, client, userdata, msg) -> None:
        """Mirrors firmware onMessage(): cmd/<id>/breaker and cmd/<id>/role."""
        topic = msg.topic
        payload = msg.payload.decode("utf-8", errors="replace").strip()
        if topic.endswith("/breaker"):
            if payload == "open":
                self.breaker_closed = False
            elif payload == "close":
                self.breaker_closed = True
            else:
                return
            self.publish_tag("breaker_status", 1 if self.breaker_closed else 0)
            print(f"[{self.short}] breaker -> {'CLOSED' if self.breaker_closed else 'OPEN'} "
                  f"(via {topic})")
        elif topic.endswith("/role"):
            # Real firmware persists to NVS and reboots. It also only implements
            # grid physics, so a non-grid role keeps publishing grid. The sim
            # acknowledges the command and does the same thing: nothing.
            print(f"[{self.short}] role command '{payload}' acknowledged "
                  f"(FW 1.0.0-grid stores role but only implements grid -- ADR-0002)")

    def disconnect(self) -> None:
        if not self.client:
            return
        # Graceful shutdown: publish offline explicitly, since a clean
        # disconnect means the broker will NOT fire the LWT.
        self.client.publish(f"{self.topic_base}/status", "offline", qos=0, retain=True)
        time.sleep(0.05)
        self.client.loop_stop()
        self.client.disconnect()

    # -- physics: line-for-line port of updatePhysics() ---------------------
    def update_physics(self) -> None:
        self.load_walk = self._constrain(
            self.load_walk + self._arnd(-20, 21) / 1000.0, 0.30, 0.95)

        # firmware: 0.10 * sinf((millis()/600000.0) * 6.2832)
        # millis() is board uptime. Deriving it from the tick counter rather
        # than the wall clock keeps the sim deterministic: same board short =>
        # same stream, every run. Reading time.time() here would make two
        # feeders with identical identity diverge, which would quietly break
        # the reproducibility this file claims.
        self.ticks += 1
        millis = self.ticks * PUBLISH_S * 1000.0
        diurnal = 0.10 * math.sin((millis / 600000.0) * 6.2832)

        self.cur_load = self._constrain(
            self.load_walk + diurnal + self.offset, 0.20, 0.99)

        # THE line. Voltage sags against curLoad; current is driven by ld, which
        # zeroes on an open breaker. So current collapses and voltage HOLDS.
        ld = self.cur_load if self.breaker_closed else 0.0

        for i in range(3):
            imbalance = 1.0 + ((i - 1) * 0.004)
            self.V[i] = (V_NOM * (1.0 - V_SAG * self.cur_load)) * imbalance \
                + self._arnd(-30, 31)
            self.I[i] = ((I_BASE + I_SPAN * ld) * imbalance + self._arnd(-8, 9)) \
                if self.breaker_closed else float(self._arnd(0, 3))

        # Bounded random walk pulled to nominal. NOT load-coupled -- the
        # reference docs claimed it was; the firmware disagrees (ADR-0002).
        self.freq += self._arnd(-4, 5) / 1000.0
        self.freq += (F_NOM - self.freq) * 0.05
        self.freq = self._constrain(self.freq, 59.95, 60.05)

        self.pf = self._constrain(
            PF_BASE - PF_SLOPE * ld + self._arnd(-5, 6) / 1000.0, 0.90, 0.995)

        p_sum = sum(self.V[i] * self.I[i] for i in range(3))
        self.kw = (p_sum * self.pf) / 1000.0

        # First-order thermal integrator. tau ~= 66 s. Ceiling ~74.7 C, so the
        # 80 C red band is unreachable from load alone -- by design (ADR-0002).
        self.temp += ((T_BASE + T_SPAN * ld) - self.temp) * T_ALPHA

    # -- wire format: exactly publishTag() ----------------------------------
    def publish_tag(self, tag: str, value: float) -> None:
        if not self.client:
            return
        # firmware: {"value":%.3f,"device":"%s"} -- NO timestamp field.
        payload = json.dumps({"value": round(float(value), 3), "device": self.device})
        self.client.publish(f"{self.topic_base}/{tag}", payload)

    def publish_grid(self) -> None:
        """The canonical 11 tags, in firmware's publishGrid() order."""
        self.publish_tag("voltage_a", self.V[0])
        self.publish_tag("voltage_b", self.V[1])
        self.publish_tag("voltage_c", self.V[2])
        self.publish_tag("current_a", self.I[0])
        self.publish_tag("current_b", self.I[1])
        self.publish_tag("current_c", self.I[2])
        self.publish_tag("frequency", self.freq)
        self.publish_tag("power_factor", self.pf)
        self.publish_tag("real_power_kw", self.kw)
        self.publish_tag("transformer_temp", self.temp)
        # 1 = closed (normal), 0 = open. No inversion. Ever.
        self.publish_tag("breaker_status", 1 if self.breaker_closed else 0)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Simulate the six-board ESP32 grid fleet (no hardware).",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--boards", type=int, default=len(DEFAULT_BOARDS),
                    metavar="N", help=f"how many feeders (1-{len(DEFAULT_BOARDS)})")
    ap.add_argument("--trip-after", type=float, metavar="SECONDS",
                    help="open a breaker after N seconds (the cascade demo)")
    ap.add_argument("--trip-board", metavar="SHORT",
                    help="which feeder to trip (default: the first)")
    args = ap.parse_args()

    if not MQTT_PASS:
        return int(bool(sys.stderr.write(
            "[sim] MQTT_FIELD_PASSWORD is not set.\n"
            "      cp .env.example .env and fill it in, then:\n"
            "        set -a; source .env; set +a\n")) )

    shorts = DEFAULT_BOARDS[:max(1, min(args.boards, len(DEFAULT_BOARDS)))]
    trip_target = args.trip_board or shorts[0]
    if args.trip_after and trip_target not in shorts:
        print(f"[sim] --trip-board {trip_target} is not in the active fleet: {shorts}")
        return 1

    feeders = [Feeder(s) for s in shorts]
    print(f"[sim] SIMULATOR -- not firmware, nothing is flashed.")
    print(f"[sim] {len(feeders)} feeders -> {MQTT_HOST}:{MQTT_PORT} as {MQTT_USER}, "
          f"every {PUBLISH_S:.0f}s")
    for f in feeders:
        f.connect()
        print(f"[sim]   {f.device}  offset={f.offset:+.3f}  -> grid/{f.short}/#")
    if args.trip_after:
        print(f"[sim] feeder {trip_target} breaker will OPEN at t+{args.trip_after:.0f}s")
        print(f"[sim] watch: current and real_power collapse, VOLTAGE HOLDS.")
    print("[sim] Ctrl-C to stop.\n")

    running = True

    def _stop(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    started = time.time()
    tripped = False
    try:
        while running:
            elapsed = time.time() - started
            if args.trip_after and not tripped and elapsed >= args.trip_after:
                for f in feeders:
                    if f.short == trip_target:
                        f.breaker_closed = False
                        print(f"[sim] *** BREAKER OPEN on {f.short} at t+{elapsed:.0f}s "
                              f"-- current collapses, voltage holds ***")
                tripped = True

            for f in feeders:
                f.update_physics()
                f.publish_grid()

            time.sleep(PUBLISH_S)
    finally:
        print("\n[sim] stopping; marking feeders offline…")
        for f in feeders:
            f.disconnect()
        print("[sim] stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
