# Hardware Bill of Materials

The physical lab behind the grid substation twin. Nothing here is required to
run the twin itself — it ships with a simulator (see `docs/quickstart.md`). This
BOM is for reproducing the full live pipeline.

## Field layer (Level 1) — the fleet

| Qty | Item | Role in lab | Notes |
|----|------|-------------|-------|
| 6 | ELEGOO ESP32 Dev Module (USB-C, CP2102) | Field devices running `universal_field.ino` | CP2102 driver needed on Windows |
| 1 | Powered USB hub | Powers/flashes the fleet | |
| 1 | 35 mm TS35 DIN rail + carriers | Mounts the fleet as a "field device layer" | Portfolio presentation; optional |

Only the grid role has live physics in FW 1.0.0-grid. All six boards run the
same binary and default to `role=grid`.

## Historian / broker (Level 3 / 3.5)

| Qty | Item | Hosts | Address |
|----|------|-------|---------|
| 1 | Synology DS224+ NAS | Mosquitto, InfluxDB, Grafana, mqtt-bridge (Docker) | 192.168.1.163 |
| 1 | KAMRUI Pinova P2 Mini PC (Ryzen 4300U, 16 GB) | Proxmox — OPNsense, Kali, twin backend (future) | 192.168.1.50 |

## Control / supervisory (Level 2 / 3)

| Qty | Item | Role | Status |
|----|------|------|--------|
| 1 | Raspberry Pi 4 (4 GB) | Ignition SCADA | Running · 192.168.1.153 |
| 1 | Raspberry Pi 3B | OpenPLC | Planned |

## Networking (Loop 4 segmentation — planned)

| Qty | Item | Role |
|----|------|------|
| 1 | MikroTik hEX RB750Gr3 | Lab gateway / VLAN segmentation |
| 1 | TP-Link TL-SG108E | Managed switch |
| 1 | Verizon G3100 | ISP router (flat 192.168.1.0/24 today) |

> VLAN segmentation is not yet live. Until it is, see ADR-0004 (IPv6 exposure)
> and SAFETY.md invariant #8. Do not expose this lab to an untrusted network.

## Security / research tooling

| Qty | Item | Role |
|----|------|------|
| 1 | Flipper Zero | RF / protocol analysis |
| 1 | RTL-SDR | Software-defined radio |
| 1 | Kali (Proxmox LXC + Kasm) | Attack platform — offensive work is out of V1 scope, ADR-0007 |
