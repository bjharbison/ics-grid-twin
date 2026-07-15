# Architecture

## Purdue-model placement

```mermaid
flowchart TB
  subgraph L4["Level 4 — Enterprise / IT"]
    LAP["Laptop · Arduino IDE · fleet manager GUI"]
  end
  subgraph L35["Level 3.5 — IT/OT DMZ (DS224+)"]
    MQ["Mosquitto broker :1883"]
    BR["mqtt-bridge"]
  end
  subgraph L3["Level 3 — Operations / Historian"]
    IN["InfluxDB :8086"]
    GF["Grafana :3000"]
    TW["Grid twin (HTML)"]
  end
  subgraph L1["Level 1 — Field devices"]
    E1["ESP32 · grid/&lt;short&gt;/#"]
    E2["ESP32 · grid/&lt;short&gt;/#"]
    E3["...6 boards"]
  end

  E1 -- "telemetry (pub)" --> MQ
  E2 --> MQ
  E3 --> MQ
  MQ --> BR --> IN --> GF
  IN -. "replay/backfill" .-> TW
  MQ -. "live (read-only)" .-> TW
  LAP -- "cmd/&lt;short&gt;/# (scada-server)" --> MQ
  MQ -- "commands (sub)" --> E1
```

## Data path

```
ESP32 fleet
   │  MQTT publish, every 2 s, {"value":<float>,"device":"grid-substation-<short>"}
   ▼
Mosquitto broker  203.0.113.163:1883   (default-deny ACL)
   │  monitor-reader subscribes #
   ▼
mqtt-bridge  →  InfluxDB line protocol   (measurement=grid, tags board_id+device)
   ▼
InfluxDB  203.0.113.163:8086   org "ICS Lab" · bucket ics-telemetry
   ▼
Grafana dashboard  ·and·  grid twin (live or replay)
```

## Command path (supervisory)

```
fleet manager (scada-server)  →  cmd/<short>/breaker  "open"|"close"
                                 cmd/<short>/role     "<rolename>"
   broker delivers to board's  cmd/<short>/#  subscription
   → firmware onMessage() acts, re-publishes breaker_status
```

A clean publish proves only that the broker accepted the message. Delivery
depends on the `esp32-field` ACL granting `topic read cmd/#`. See ADR-0003.

## The one signature that matters

Opening a breaker collapses **feeder current and real power** while **bus
voltage holds**. That asymmetry — not a blackout — is the Industroyer / 2016
Ukraine signature, and it is what the twin, the dashboard, and the physics port
are all built to make legible. A model that de-energizes the bus on breaker-open
is showing an event that didn't happen.
