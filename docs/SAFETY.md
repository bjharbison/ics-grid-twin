# SAFETY.md

The canonical safety document for this repo. Everything else defers to it. It
maps each **invariant** to the **mechanism** that enforces it and the
**evidence** that the mechanism works. Where an invariant is not yet fully
enforced, it says so — an honest "Open" is worth more than a false "green."

This lab simulates OT systems; it does not control physical processes. But it is
built to OT-security discipline deliberately, because that discipline is the
portfolio point.

## Invariant → mechanism → evidence

| # | Invariant | Mechanism | Evidence | Status |
|---|-----------|-----------|----------|--------|
| 1 | No credential is ever committed | `.env`/`secrets.h` gitignored; only `*.example` templates ship; gitleaks + detect-private-key pre-commit gate | `.gitignore`, `.pre-commit-config.yaml`, `pre-commit run --all-files` clean | ✅ Enforced |
| 2 | Previously-exposed secrets are invalidated | Rotate InfluxDB token + broker/Grafana passwords out-of-band | Release checklist item; ADR-0005 | ⚠️ Manual — do before publish |
| 3 | The read path holds no write capability | Fleet manager uses two MQTT clients: always-on `monitor-reader` (read), on-demand `scada-server` (command); read-only is the default | `fleet-manager/esp32_fleet.py` `FleetMQTT`; command buttons disabled without `MQTT_CMD_PASSWORD` | ✅ Enforced |
| 4 | Field devices cannot read each other's commands or over-publish | Mosquitto default-deny ACL; `esp32-field` limited to `grid/#` write + `cmd/#` read; reserved roles NOT pre-granted | `infra/mosquitto/config/acl.example`; ADR-0003 | ✅ Enforced |
| 5 | A command that the broker accepts is not assumed delivered | Fleet manager logs, after every publish, that broker-acceptance ≠ delivery and effect must be confirmed in telemetry | `send_command()` warning; ADR-0003 | ✅ Enforced |
| 6 | breaker_status polarity is never silently flipped | Single source of truth: `1 = closed`, verified against firmware; asserted in fleet manager, twin, dashboard, and a unit check | ADR-0002 §2; estimator test output | ✅ Enforced |
| 7 | The twin reflects firmware behaviour, not a plausible guess | Twin physics is a line-for-line port of `updatePhysics()`; constants diffed against `.ino` in CI-style check | Constant-diff check (all 10 constants match) | ✅ Enforced |
| 8 | OT devices have no route to the internet | Planned VLAN (Loop 4) + OPNsense egress deny | **Not yet enforced** — IPv6 global-unicast addresses observed on lab devices bypass the IPv4-only plan | 🔲 Open — ADR-0004 |
| 9 | Twins/tools are never a network exception to the OT boundary | Compose stack binds LAN-local; docs forbid port-forwarding; twin live-path documented behind the boundary | `infra/docker-compose.yml` header; twin MQTT comment | ✅ By design (pending #8) |
| 10 | Offensive capability is not shipped in V1 | Detection/visualization only; attack scenarios described and simulated, never weaponized | ADR-0007; no Modbus-write code in tree | ✅ Enforced |
| 11 | The twin can observe but never actuate | Twin subscribes only; zero `.publish()` calls; sim controls disabled while live; connects as `monitor-reader` | `verify_physics.py` read-only check | ✅ Enforced |
| 12 | Stale data is never rendered as live | Wall-clock staleness watchdog (5 missed intervals) + LWT `offline` handling; stale state visibly desaturates and greys the model | `twin/grid_twin.html` staleness interval; `body.stale` CSS | ✅ Enforced |
| 15 | The mock fleet cannot drift from firmware | Sim asserts firmware tag names, per-board topics, `1 = closed`, no timestamp, physics constants, and voltage-holds-on-trip | `verify_physics.py` mock-fleet block; CI `invariants` job; ADR-0009 | ✅ Enforced |
| 16 | Invariants are checked on every push, not just locally | GitHub Actions: gitleaks over full history, assert-no-secret-files-tracked, invariant suite, config sanity, twin JS parse | `.github/workflows/ci.yml` | ✅ Enforced |
| 14 | Dependencies actually run as pinned | All MQTT clients go through a `make_client()` factory compatible with paho 1.x and 2.x; no bare constructors | `verify_physics.py` paho checks; ADR-0008 | ✅ Enforced |
| 13 | Live credentials are never persisted by the twin | Entered per-tab in a dialog, held in memory only; no localStorage, no config file, no query param | `verify_physics.py` storage check | ✅ Enforced |

## How to re-verify

```bash
pre-commit run --all-files                    # invariant 1
python fleet-manager/verify_physics.py        # invariants 6, 7, 11-15 (offline, no broker)
grep -rn "MQTT_CMD_PASSWORD" fleet-manager/    # invariant 3
cat infra/mosquitto/config/acl.example         # invariant 4
```

## Open items (tracked honestly)

* **#2 rotation** — do before first public push. Independent of the scrub.
* **#8 IPv6** — remains Open until Loop 4 lands and a global-unicast v6 probe of
  the OT segment comes back empty. This is the most important open item and is
  deliberately foregrounded rather than buried.
