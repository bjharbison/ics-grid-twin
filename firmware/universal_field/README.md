# universal_field firmware (FW 1.0.0-grid)

One binary for the whole ESP32 fleet. Identity from MAC, role in NVS, telemetry
over MQTT, control plane over HTTP + MQTT, updates over OTA.

## Flash

1. `cp secrets.h.example secrets.h` and fill in WiFi + MQTT + OTA values (from
   Vaultwarden). `secrets.h` is gitignored.
2. Arduino IDE → board **ESP32 Dev Module** → first flash over **USB** (the OTA
   handler doesn't exist until this firmware is on the board).
3. Later reflashes can go over the air via ArduinoOTA.

## Libraries
`PubSubClient`, `ArduinoOTA`, `ESPmDNS`, `WebServer`, `Preferences` (all from the
Arduino ESP32 core). `WiFi.macAddress()` is used deliberately over
`esp_read_mac()` — see ADR-0001.

## What it publishes (grid role)

`grid/<short>/<tag>` every 2 s, payload `{"value":<float>,"device":"grid-substation-<short>"}`:

```
voltage_a  voltage_b  voltage_c        7.2 kV φ-N nominal, sags with load
current_a  current_b  current_c        collapses on breaker open
frequency                              bounded walk toward 60.00 Hz (NOT load-coupled)
power_factor  real_power_kw            pf drops with load; kw = V·I·PF
transformer_temp                       first-order thermal lag toward 45+30·load
breaker_status                         1 = closed (normal), 0 = open  ← no inversion
```

Plus `grid/<short>/status` — a retained bare string `"online"`/`"offline"`
(LWT), **not** JSON.

## Control

```
HTTP  GET  /info                board id, role, uptime, breaker, load
      GET  /roles               active + reserved roles
      POST /role?role=<name>    persist role to NVS, reboot
MQTT  cmd/<short>/breaker       "open" | "close"
      cmd/<short>/role          "<rolename>"   (persist + reboot)
      cmd/all/#                 broadcast
```

Requires the broker ACL to grant `esp32-field` `topic read cmd/#`, or commands
are silently dropped — see ADR-0003.

## Reserved roles

`substation`, `water`, `bms`, `datacenter`, `pipeline` are reserved slots so the
fleet architecture stays intact, but only `grid` has physics in this build. A
board set to another role persists it and reboots, but keeps publishing the grid
model. Full role physics ship over OTA in V2.
