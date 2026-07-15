# Quickstart

Two paths. Pick one.

## A. Just the twin, no hardware (30 seconds)

The grid substation twin is a single self-contained HTML file with a built-in
physics simulator — a line-for-line port of the real firmware. No broker, no
boards, no build step.

```bash
git clone https://github.com/VerdunHere/ics-grid-twin.git
cd ics-grid-twin
open twin/grid_twin.html        # or double-click it, or drag into a browser
```

Then:

1. Watch the eleven tags update on the shared load factor.
2. Click **Trip breaker** — current and real power collapse, **bus voltage
   holds**. That asymmetry is the whole point (see `docs/architecture.md`).
3. Click **Run Industroyer scenario** for the narrated attack sequence.

This is the fastest way to see what the project is about.

## B. Run the WHOLE pipeline with no hardware (5 minutes)

Broker, historian, dashboard, twin, and fleet manager — all of it — driven by a
six-feeder simulator standing in for the ESP32s.

```bash
cd infra
cp .env.example .env                    # fill in; any passwords you like, it's local
cp mosquitto/config/acl.example mosquitto/config/acl
# create the broker password file (see docs/data-pipeline.md step 1)
docker compose --profile sim up -d
```

Then:

- **Grafana** → `http://localhost:3000` → "ICS Grid Substation — Fleet". Both
  rows populate: six feeders publishing, six breakers closed, and a per-feeder
  drilldown.
- **The twin** → open `twin/grid_twin.html`, **Connect to fleet…**, port `9001`,
  `monitor-reader`. It discovers all six feeders.
- **The fleet manager** → `python fleet-manager/esp32_fleet.py`. Set
  `MQTT_CMD_PASSWORD` and you can actually trip a simulated breaker and watch the
  cascade land in Grafana and the twin.

Or run the simulator directly, without Docker:

```bash
cd scripts && pip install -r requirements.txt
set -a; source ../.env; set +a
python mock_fleet.py --trip-after 60        # trips a feeder after a minute
```

The simulator's physics is a line-for-line port of the firmware — same
constants, same coupling, same wire format — so what you see here is what the
real boards do. CI asserts they stay in agreement (ADR-0009).

## C. Run the full live pipeline (with the fleet)

For the real thing — six ESP32s publishing over MQTT into InfluxDB, Grafana, and
the twin.

1. **Historian stack** — follow `docs/data-pipeline.md` to bring up Mosquitto,
   InfluxDB, Grafana, and the bridge via `infra/docker-compose.yml`.
2. **Firmware** — in `firmware/universal_field/`, `cp secrets.h.example
   secrets.h`, fill it in, and flash all boards over USB (Arduino IDE, board
   "ESP32 Dev Module"). First flash must be USB; later ones can be OTA.
3. **Fleet manager** — supervisory console:
   ```bash
   cd fleet-manager
   python -m venv .venv && . .venv/bin/activate
   pip install -r requirements.txt
   cp ../.env.example ../.env      # fill in MQTT_PASSWORD (read-only) from Vaultwarden
   python esp32_fleet.py
   ```
   Leave `MQTT_CMD_PASSWORD` blank to stay read-only (recommended). Set it only
   when you intend to send breaker/role commands.
4. **Live twin** — open `twin/grid_twin.html`, click **Connect to fleet…**, and
   enter your broker host, WebSocket port (`9001`), and the read-only
   `monitor-reader` credentials. It discovers publishing feeders from
   `grid/+/status` and renders the one you pick.

   The broker needs a WebSocket listener — browsers can't open raw TCP sockets,
   so port 1883 is unreachable from a page. `infra/mosquitto/config/mosquitto.conf`
   already includes `listener 9001` + `protocol websockets`, and compose
   publishes the port.

   The twin is read-only by construction: it subscribes and never publishes, and
   the trip/scenario buttons disable while live. Actuation is the fleet manager's
   job. If a board stops publishing, the model visibly greys out rather than
   freezing on its last value.

## Before you push this repo public

- [ ] `pre-commit run --all-files` passes (install: `pip install pre-commit && pre-commit install`)
- [ ] **Rotate** the InfluxDB token and broker/Grafana passwords that lived in old plaintext notes — scrubbing the repo does not un-expose them (ADR-0005)
- [ ] `python fleet-manager/verify_physics.py` passes
- [ ] Resolve or explicitly accept the IPv6 exposure item (ADR-0004 / SAFETY.md #8)
