# Data pipeline — bring-up

How to stand up Mosquitto, InfluxDB, Grafana, and the bridge. All four run from
one `docker compose` in `infra/`.

## 1. Configure

```bash
cd infra
cp .env.example .env          # fill in from Vaultwarden; .env is gitignored
cp mosquitto/config/acl.example mosquitto/config/acl
```

Generate the broker password file (one entry per MQTT user):

```bash
docker run --rm -v "$PWD/mosquitto/config:/c" eclipse-mosquitto:2 \
  mosquitto_passwd -b -c /c/passwd monitor-reader  'YOUR_READ_PW'
docker run --rm -v "$PWD/mosquitto/config:/c" eclipse-mosquitto:2 \
  mosquitto_passwd -b    /c/passwd scada-server    'YOUR_CMD_PW'
docker run --rm -v "$PWD/mosquitto/config:/c" eclipse-mosquitto:2 \
  mosquitto_passwd -b    /c/passwd esp32-field     'YOUR_FIELD_PW'
```

Use the same values in `.env` and in the boards' `secrets.h`.

## 2. Bring it up

```bash
docker compose up -d
docker compose ps            # all four healthy
```

InfluxDB self-initializes org/bucket/token from `.env` on first run. The org
name is **case- and space-sensitive**: `ICS Lab`, not `ics-lab`. A `404` from
the bridge is almost always this.

## 3. Verify each hop

```bash
# broker sees telemetry (once boards publish)
docker exec mosquitto mosquitto_sub -u monitor-reader -P 'YOUR_READ_PW' \
  -t 'grid/#' -v -W 8

# bridge is writing
docker compose logs -f mqtt-bridge      # look for "written=N"

# influx has points
docker exec influxdb influx query --org 'ICS Lab' \
  'from(bucket:"ics-telemetry") |> range(start:-5m) |> filter(fn:(r)=> r._measurement=="grid") |> count()'
```

## 4. Grafana

Open `http://<host>:3000`, log in with the `.env` admin creds. The InfluxDB
datasource and the fleet dashboard auto-provision (see
`infra/grafana/provisioning/`). If importing the dashboard manually instead,
use `infra/grafana/dashboards/grid-fleet.json` and pick the InfluxDB datasource
when prompted.

## No hardware? Run the mock fleet

```bash
docker compose --profile sim up -d          # six simulated feeders start publishing
docker compose logs -f mock-fleet
```

Everything downstream — bridge, InfluxDB, Grafana, twin, fleet manager — behaves
exactly as it does with real boards, because the simulator reproduces the
firmware's wire format and physics faithfully. See `scripts/mock_fleet.py`.

## Synthetic value (single point, no hardware)

Publish one point and watch it traverse the whole pipeline:

```bash
docker exec mosquitto mosquitto_pub -u scada-server -P 'YOUR_CMD_PW' \
  -t 'grid/aabbcc/voltage_a' -m '{"value":7180.0,"device":"grid-substation-aabbcc"}'
```

It should appear in `mosquitto_sub`, then in the bridge log, then in InfluxDB
within a couple of seconds.

## Troubleshooting

| Symptom | Cause | Fix |
|--------|-------|-----|
| bridge: `404` on write | org name mismatch | It's `ICS Lab`, exactly |
| commands publish OK but nothing happens | `esp32-field` missing `topic read cmd/#` | Add it to `acl`, restart mosquitto (ADR-0003) |
| bridge can't reach broker | using hostname not IP from outside compose | Inside compose use service name `mosquitto`; from the NAS use the IP |
| status topic spams parse errors | parsing `grid/<short>/status` as JSON | It's a bare string; bridge already special-cases it |
| Grafana panels empty | datasource org/bucket wrong | Check provisioning picked up `.env` |
