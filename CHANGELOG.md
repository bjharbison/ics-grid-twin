# Changelog

All notable changes to this project are documented here.
Format loosely follows Keep a Changelog; this project uses semantic-ish tags.

## [1.0.0] — 2026-07-15

First public release. Grid substation twin + fleet lab.

### Added
- Self-contained grid substation digital twin (`twin/grid_twin.html`) with a
  built-in physics simulator ported line-for-line from firmware. Runs with no
  hardware.
- Validated universal ESP32 firmware (`firmware/universal_field/`, FW
  1.0.0-grid) with `secrets.h` template.
- ESP32 fleet manager console (`fleet-manager/esp32_fleet.py`), read-only by
  default, dual-account command path, rebuilt for the canonical `cmd/<short>/#`
  scheme.
- Historian stack (`infra/`): docker-compose for Mosquitto, InfluxDB, Grafana,
  and the MQTT→InfluxDB bridge with `board_id`/`device` tagging.
- Importable Grafana fleet dashboard (fleet overview + per-feeder drilldown).
- Docs: SAFETY.md invariant table, architecture (mermaid), quickstart,
  data-pipeline, hardware BOM, and a 7-record ADR set.
- Offline physics/polarity verification (`fleet-manager/verify_physics.py`).
- Secret-scanning pre-commit config.
- `scripts/mock_fleet.py` — six-feeder fleet simulator. Faithful line-for-line
  port of firmware physics; per-board MAC-derived offsets, retained birth/LWT,
  per-board `cmd/<short>/#` subscription, deterministic. Runs the entire pipeline
  with no hardware. Also a compose profile: `docker compose --profile sim up`.
- GitHub Actions CI: gitleaks over full history, assert-no-secret-files-tracked,
  the invariant suite as a build gate, config sanity, twin JS parse.
- `docs/frameworks/` — IEC 62443 zones & conduits (with honest SL-T vs SL-A),
  NIST SP 800-82r3 control mapping, Zero Trust (SP 800-207), Unified Namespace.
- Live MQTT path in the twin (`Connect to fleet…`): feeder discovery from
  `grid/+/status`, read-only subscription, wall-clock staleness watchdog, LWT
  offline handling. Simulator and live feed share one state object.
- Mosquitto WebSocket listener (`:9001`) so browsers can reach the broker.
- Scripted, seed-reproducible demo GIF capture (`tools/capture_demo.py`).

### Fixed / corrected
- **paho-mqtt 2.0 incompatibility** in the fleet manager and the bridge: pinned
  `>=2.0` while constructing clients the 1.x way, which raises `ValueError` at
  startup. All clients now route through a `make_client()` factory supporting
  both majors; pins widened to `>=1.6,<3.0` (ADR-0008).
- Command-topic drift: retired the older `fleet/<id>/cmd` scheme in favour of the
  validated `cmd/<short>/#` scheme fleet-wide (ADR-0003).
- Six firmware-vs-docs corrections adopted (tag names, breaker polarity, two
  undocumented tags, frequency coupling, thermal ceiling, status payload shape)
  (ADR-0002).

### Notes
- A parallel repository built from the reference docs rather than the firmware
  was compared and retired rather than merged; it inverted breaker polarity and
  modelled a trip as full de-energization. Its good ideas (fleet simulator, CI,
  framework docs) were re-implemented against firmware (ADR-0009).

### Known open items
- IPv6 global-unicast exposure vs. the no-internet-route invariant (ADR-0004).
- Credential rotation for previously-exposed secrets is a manual release step
  (ADR-0005).
