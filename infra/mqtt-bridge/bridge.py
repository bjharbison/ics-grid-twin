#!/usr/bin/env python3
"""
bridge.py -- Mosquitto -> InfluxDB bridge for the ICS grid substation lab.

Subscribes to the fleet's telemetry as the read-only `monitor-reader` account
and writes each message into InfluxDB as a time-series point. No filtering --
everything published is persisted, including anomalous values. A bridge that
drops outliers would erase exactly the evidence an attack demo needs.

TAGGING SCHEMA
--------------
An early version tagged points with the full topic path as a single `source`
tag, which made per-board Flux queries painful. `board_id` and `device` are
now separate tags, which is what makes both fleet-aggregate and per-feeder
drilldown queries clean. See docs/adr/0006-influx-tagging.md

    MQTT   grid/4d2238/voltage_a  {"value": 7185.2, "device": "grid-substation-4d2238"}
      ->
    Influx measurement=grid
           tags:   board_id=4d2238, device=grid-substation-4d2238
           field:  voltage_a=7185.2
           time:   arrival time (the payload carries no timestamp)

TIMESTAMP OWNERSHIP
-------------------
The firmware's payload has no timestamp field -- verified against
universal_field.ino publishTag(). Arrival time at the bridge is therefore the
only clock. That is fine at a 2s publish interval on a LAN, but it means
replayed history has timestamps live data never carried. Worth remembering
when comparing a replay against a live run.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time

import paho.mqtt.client as mqtt
import requests

# paho-mqtt 2.0 made `callback_api_version` a required first argument to
# Client(); the 1.x-style constructor raises ValueError at startup. Callbacks
# here are VERSION1-shaped, so request VERSION1 on 2.x and fall back on 1.x.
try:
    _CALLBACK_V1 = mqtt.CallbackAPIVersion.VERSION1      # paho >= 2.0
except AttributeError:
    _CALLBACK_V1 = None                                  # paho 1.x


def make_client(client_id: str) -> "mqtt.Client":
    if _CALLBACK_V1 is not None:
        return mqtt.Client(_CALLBACK_V1, client_id=client_id)
    return mqtt.Client(client_id=client_id)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("bridge")

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "monitor-reader")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

INFLUX_URL = os.getenv("INFLUX_URL", "http://influxdb:8086").rstrip("/")
INFLUX_ORG = os.getenv("INFLUX_ORG", "ICS Lab")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "ics-telemetry")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "")

# Role topic roots the bridge will ingest. Only grid is live today; the rest
# are here so a new role starts flowing the moment its physics ships.
TOPIC_ROOTS = ("grid", "dc", "water", "bms", "pipeline")

# Topic leaves that are not telemetry.
NON_TAG_LEAVES = {"status"}


def _escape_tag(value: str) -> str:
    """Influx line protocol: commas, spaces and equals must be escaped in tags."""
    return value.replace("\\", "\\\\").replace(",", "\\,").replace(" ", "\\ ").replace("=", "\\=")


def _measurement_for(parts: list[str]) -> str:
    """
    Map a topic to a measurement name.

      grid/4d2238/voltage_a  -> grid
      dc/power/pdu_load      -> dc_power     (multi-root roles keep their subtree)
    """
    if parts[0] == "dc" and len(parts) >= 3 and parts[1] in ("power", "cooling", "env"):
        return f"dc_{parts[1]}"
    return parts[0]


class Bridge:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Token {INFLUX_TOKEN}",
                "Content-Type": "text/plain; charset=utf-8",
            }
        )
        self.write_url = f"{INFLUX_URL}/api/v2/write"
        self.written = 0
        self.dropped = 0

    def wait_for_influx(self, timeout: int = 120) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = self.session.get(f"{INFLUX_URL}/health", timeout=5)
                if r.ok:
                    log.info("influxdb healthy at %s", INFLUX_URL)
                    return
            except requests.RequestException:
                pass
            log.info("waiting for influxdb…")
            time.sleep(3)
        log.warning("influxdb health check timed out; continuing anyway")

    def write(self, line: str) -> None:
        try:
            r = self.session.post(
                self.write_url,
                params={"org": INFLUX_ORG, "bucket": INFLUX_BUCKET, "precision": "ms"},
                data=line.encode("utf-8"),
                timeout=10,
            )
            if r.status_code >= 300:
                self.dropped += 1
                # A 404 here is almost always the org name. It is case- and
                # space-sensitive: "ICS Lab", not "ics-lab" or "ICS_LAB".
                log.error("influx write %s: %s | line=%s", r.status_code, r.text[:200], line)
            else:
                self.written += 1
                if self.written % 250 == 0:
                    log.info("written=%d dropped=%d", self.written, self.dropped)
        except requests.RequestException as e:
            self.dropped += 1
            log.error("influx write failed: %s", e)

    # -- mqtt callbacks ----------------------------------------------------
    def on_connect(self, client, userdata, flags, rc) -> None:
        if rc != 0:
            log.error("mqtt connect failed rc=%s (%s)", rc, mqtt.connack_string(rc))
            return
        log.info("mqtt connected to %s:%s as %s", MQTT_HOST, MQTT_PORT, MQTT_USER)
        for root in TOPIC_ROOTS:
            client.subscribe(f"{root}/#", qos=0)
            log.info("subscribed %s/#", root)

    def on_disconnect(self, client, userdata, rc) -> None:
        log.warning("mqtt disconnected rc=%s; retrying", rc)

    def on_message(self, client, userdata, msg) -> None:
        parts = msg.topic.split("/")
        if len(parts) < 3 or parts[0] not in TOPIC_ROOTS:
            return

        board_id, leaf = parts[1], parts[-1]

        # grid/<short>/status is a bare string ("online"/"offline"), not JSON.
        # Parsing it as telemetry would spam errors on every board reconnect.
        if leaf in NON_TAG_LEAVES:
            log.info("status %s -> %s", board_id, msg.payload.decode(errors="replace").strip())
            return

        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            value = float(payload["value"])
        except (ValueError, KeyError, TypeError, UnicodeDecodeError) as e:
            log.warning("unparseable payload on %s: %s", msg.topic, e)
            return

        device = str(payload.get("device", "")) or board_id
        measurement = _measurement_for(parts)

        line = (
            f"{measurement},board_id={_escape_tag(board_id)},device={_escape_tag(device)} "
            f"{leaf}={value} {int(time.time() * 1000)}"
        )
        self.write(line)


def main() -> None:
    missing = [k for k, v in (("MQTT_PASSWORD", MQTT_PASSWORD), ("INFLUX_TOKEN", INFLUX_TOKEN)) if not v]
    if missing:
        log.error("missing required env: %s -- see infra/.env.example", ", ".join(missing))
        sys.exit(1)

    b = Bridge()
    b.wait_for_influx()

    client = make_client("mqtt-bridge")
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.on_connect = b.on_connect
    client.on_disconnect = b.on_disconnect
    client.on_message = b.on_message

    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            break
        except OSError as e:
            log.warning("broker not reachable (%s); retrying in 3s", e)
            time.sleep(3)

    client.loop_forever(retry_first_connection=True)


if __name__ == "__main__":
    main()
