# ESP32 Fleet Manager

A Level-3 supervisory console for the ESP32 field fleet. It reads telemetry as
it flows up through the broker and issues supervisory commands back down through
the broker — it does not reach into Level 1 devices directly.

```
Level 3    Fleet Manager (this app), historian, HMI
             │ subscribe grid/#          │ publish cmd/<short>/<verb>
Level 3.5  Mosquitto broker ─────────────┴──────────────────────────
Level 1    ESP32 field devices (telemetry up, commands down)
```

## Run

```bash
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example ../.env                       # fill in from Vaultwarden
python esp32_fleet.py
```

`MQTT_PASSWORD` (the read-only `monitor-reader` account) is required. Leave
`MQTT_CMD_PASSWORD` blank to stay read-only — that's the recommended default.

## What you get

A live table of every feeder the broker knows about: board id, device name,
online/stale/offline, breaker state, estimated load, phase A voltage/current,
frequency, transformer temperature, real power, and time since last message.
Rows grey out when stale, and go red on an open breaker or a hot transformer.

## Safety posture

* **Read-only by default.** Command buttons stay disabled unless a separate
  supervisory credential is supplied.
* **Two MQTT accounts, two clients.** The always-on read client
  (`monitor-reader`) never holds write capability; the command client
  (`scada-server`) connects on demand. This is deliberate — see SAFETY.md #3.
* **Commands require confirmation** naming the target feeder and stating the
  effect.
* **A clean publish is not delivery.** After every command the log says so. If
  the broker ACL is missing `topic read cmd/#` for `esp32-field`, publishes
  succeed and are silently dropped — this bit the lab once already (ADR-0003).
* **No hardcoded credentials.** Everything comes from the environment / `.env`.

## Optional direct polling

`FLEET_HTTP_POLL=true` polls each board's HTTP `/info` endpoint directly. It's
read-only and off by default, and it's the only path that touches field devices
directly — modelled deliberately as the kind of unauthenticated management
surface real OT gear exposes, and which should trip network detection once the
lab is VLAN-segmented.

## Notes on the implementation

**Load is estimated from voltage, not current.** The firmware never publishes
the load factor, so it has to be inverted from what's on the wire. Current is
the tempting basis, but the firmware zeroes current when the breaker opens while
voltage keeps sagging against the real load — so a current-based estimator reads
"no load" during exactly the event you care about. `Board.load_est` inverts the
voltage sag instead, and stays correct in both breaker states.

**breaker_status is `1 = closed`.** Verified against firmware. No inversion.
Contrast the pipeline role's `emergency_shutdown`, which *is* inverted.

**paho-mqtt 1.x and 2.x are both supported** via the `make_client()` factory.
paho 2.0 made `callback_api_version` a required argument; a 1.x-style
constructor raises `ValueError` on startup.

## Verify without hardware

```bash
python verify_physics.py
```

Checks breaker polarity, physics constants against the firmware, the load
estimator's inversion, twin read-only/no-storage invariants, and paho client
construction. No broker or boards needed.

## Verification status (honest)

Logic is unit-verified offline: the load estimator inverts to zero error, the
paho factory is proven against stubs of both major versions. The tkinter UI and
a live broker session have **not** been exercised in CI — run it against the
fleet before relying on it. Known-good path is the read-only mode.
