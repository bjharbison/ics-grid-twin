#!/usr/bin/env python3
"""
esp32_fleet.py -- ESP32 Fleet Manager console for the ICS grid substation lab.

A Level-3 supervisory console for a fleet of ESP32 field devices running
`universal_field.ino`. It reads telemetry as it flows up through the broker
(passive) and issues supervisory commands back down through the broker --
it does not reach into Level 1 devices directly.

    Level 3    Fleet Manager (this app), historian, HMI
                 | subscribe grid/#        | publish cmd/<short>/<verb>
    Level 3.5  Mosquitto broker  ----------+--------------------------
    Level 1    ESP32 field devices (telemetry up, commands down)

The one exception is the optional HTTP /info poll (FLEET_HTTP_POLL=true),
which touches devices directly. It is read-only, off by default, and is
deliberately modeled as the kind of unauthenticated management surface real
OT gear exposes -- and which should trip network detection once the lab is
VLAN-segmented.

SAFETY POSTURE
--------------
* Default is READ-ONLY. Command controls stay disabled unless a separate
  supervisory credential (MQTT_CMD_PASSWORD) is supplied.
* Telemetry and commands use two different MQTT accounts. The read path never
  holds write capability.
* Every command requires explicit confirmation naming the target board.
* No credentials are hardcoded. Everything comes from the environment / .env,
  sourced from Vaultwarden at config time.

WIRE CONTRACT (verified against universal_field.ino, FW 1.0.0-grid)
-------------------------------------------------------------------
  Telemetry : grid/<short>/<tag>   {"value": <float>, "device": "<name>"}
              -- no timestamp field; arrival time is the only clock
  Status    : grid/<short>/status  bare string "online"|"offline", retained
  Commands  : cmd/<short>/breaker  "open" | "close"
              cmd/<short>/role     "<rolename>"   (board persists + reboots)
              cmd/all/<verb>       broadcast to fleet

Usage:
    cp ../.env.example ../.env   # then fill in
    pip install -r requirements.txt
    python esp32_fleet.py
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import messagebox, ttk

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover
    raise SystemExit("paho-mqtt is required:  pip install -r requirements.txt")


# paho-mqtt 2.0 made `callback_api_version` a REQUIRED first argument to
# Client(); constructing one the 1.x way raises ValueError at startup. The
# callbacks below are VERSION1-shaped (client, userdata, flags, rc), so we ask
# for VERSION1 explicitly on 2.x and fall back to the bare constructor on 1.x.
# This keeps one file working across both major versions.
try:
    _CALLBACK_V1 = mqtt.CallbackAPIVersion.VERSION1      # paho >= 2.0
except AttributeError:
    _CALLBACK_V1 = None                                  # paho 1.x


def make_client(client_id: str) -> "mqtt.Client":
    if _CALLBACK_V1 is not None:
        return mqtt.Client(_CALLBACK_V1, client_id=client_id)
    return mqtt.Client(client_id=client_id)


# --------------------------------------------------------------------------
# Configuration -- environment only, never hardcoded
# --------------------------------------------------------------------------

def _load_dotenv() -> None:
    """Minimal .env loader. Avoids a dependency; does not override real env."""
    for candidate in (Path(__file__).parent / ".env", Path(__file__).parent.parent / ".env"):
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())
        return


_load_dotenv()

MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "monitor-reader")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_CMD_USER = os.getenv("MQTT_CMD_USER", "scada-server")
MQTT_CMD_PASSWORD = os.getenv("MQTT_CMD_PASSWORD", "")
STALE_SECONDS = float(os.getenv("FLEET_STALE_SECONDS", "10"))
HTTP_POLL = os.getenv("FLEET_HTTP_POLL", "false").lower() in ("1", "true", "yes")

TOPIC_ROOT = "grid"

# The 11 tags universal_field.ino publishes. Anything else is unexpected.
KNOWN_TAGS = (
    "voltage_a", "voltage_b", "voltage_c",
    "current_a", "current_b", "current_c",
    "frequency", "power_factor", "real_power_kw",
    "transformer_temp", "breaker_status",
)

# Firmware physics constants, used to invert for the load estimate.
# See universal_field.ino updatePhysics():
#   voltage[i] = 7250 * (1 - 0.015 * curLoad) * imbalance + noise
V_NOMINAL = 7250.0
V_SAG_COEFF = 0.015

XFMR_WARN_C = 72.0
XFMR_RED_C = 80.0


# --------------------------------------------------------------------------
# Fleet state
# --------------------------------------------------------------------------

@dataclass
class Board:
    """Latent state for one field device, keyed by MAC-tail short id."""
    short: str
    device: str = ""
    tags: dict[str, float] = field(default_factory=dict)
    lwt: str = "unknown"          # "online" / "offline" from retained status topic
    last_seen: float = 0.0

    @property
    def status(self) -> str:
        if self.lwt == "offline":
            return "OFFLINE"
        if self.last_seen and (time.time() - self.last_seen) > STALE_SECONDS:
            return "STALE"
        if self.lwt == "online":
            return "ONLINE"
        return "?"

    @property
    def breaker(self) -> str:
        v = self.tags.get("breaker_status")
        if v is None:
            return "-"
        # Verified against firmware: 1.0 = closed (normal), 0.0 = open.
        # No polarity inversion on this tag. Do not "helpfully" flip it.
        return "CLOSED" if v >= 0.5 else "OPEN"

    @property
    def load_est(self) -> float | None:
        """
        Estimate the load factor. The firmware never publishes it -- it is
        internal state -- so it must be inverted from what is on the wire.

        Voltage is the right basis, not current: the firmware sags voltage
        against `curLoad` but drives current from `ld` (which it zeroes when
        the breaker opens). So a current-based estimator reads 0 load on an
        open breaker, while the voltage-based one stays correct in both
        breaker states.
        """
        phases = [self.tags.get(f"voltage_{p}") for p in ("a", "b", "c")]
        present = [v for v in phases if v is not None]
        if not present:
            return None
        v_avg = sum(present) / len(present)
        load = (1.0 - (v_avg / V_NOMINAL)) / V_SAG_COEFF
        return max(0.0, min(1.0, load))


class FleetModel:
    """Thread-safe registry of boards, fed from the MQTT callback thread."""

    def __init__(self) -> None:
        self._boards: dict[str, Board] = {}
        self._lock = threading.Lock()

    def snapshot(self) -> list[Board]:
        with self._lock:
            return sorted(self._boards.values(), key=lambda b: b.short)

    def _get(self, short: str) -> Board:
        if short not in self._boards:
            self._boards[short] = Board(short=short)
        return self._boards[short]

    def on_status(self, short: str, payload: str) -> None:
        with self._lock:
            b = self._get(short)
            b.lwt = payload.strip()
            if b.lwt == "online":
                b.last_seen = time.time()

    def on_tag(self, short: str, tag: str, value: float, device: str) -> None:
        with self._lock:
            b = self._get(short)
            b.tags[tag] = value
            b.last_seen = time.time()
            if device:
                b.device = device


# --------------------------------------------------------------------------
# MQTT plumbing
# --------------------------------------------------------------------------

class FleetMQTT:
    """
    Two clients, deliberately:
      * read client  -- monitor-reader, subscribes grid/#
      * cmd client   -- scada-server, publish only, connected on demand

    Splitting them means the always-on connection never holds write capability.
    """

    def __init__(self, model: FleetModel, log: queue.Queue) -> None:
        self.model = model
        self.log = log
        self.read_client: mqtt.Client | None = None
        self.cmd_client: mqtt.Client | None = None
        self.connected = False

    # -- read path ---------------------------------------------------------
    def start(self) -> None:
        c = make_client(f"fleet-manager-ro-{int(time.time())}")
        c.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        c.on_connect = self._on_connect
        c.on_disconnect = self._on_disconnect
        c.on_message = self._on_message
        self.read_client = c
        c.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
        c.loop_start()

    def stop(self) -> None:
        for c in (self.read_client, self.cmd_client):
            if c:
                c.loop_stop()
                c.disconnect()
        self.connected = False

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            self.connected = True
            client.subscribe(f"{TOPIC_ROOT}/#", qos=0)
            self.log.put(("ok", f"connected to {MQTT_HOST}:{MQTT_PORT} as {MQTT_USER} (read-only)"))
        else:
            self.connected = False
            self.log.put(("err", f"connect failed rc={rc} ({mqtt.connack_string(rc)})"))

    def _on_disconnect(self, client, userdata, rc) -> None:
        self.connected = False
        self.log.put(("warn", f"disconnected (rc={rc}); paho will retry"))

    def _on_message(self, client, userdata, msg) -> None:
        try:
            parts = msg.topic.split("/")
            # grid/<short>/<leaf>
            if len(parts) != 3 or parts[0] != TOPIC_ROOT:
                return
            short, leaf = parts[1], parts[2]
            raw = msg.payload.decode("utf-8", errors="replace").strip()

            # Status is a BARE STRING, not JSON -- unlike every other topic
            # under grid/#. Verified against firmware connectMQTT().
            if leaf == "status":
                self.model.on_status(short, raw)
                return

            payload = json.loads(raw)
            value = float(payload["value"])
            device = str(payload.get("device", ""))
            if leaf not in KNOWN_TAGS:
                self.log.put(("warn", f"unexpected tag {short}/{leaf} -- firmware drift?"))
            self.model.on_tag(short, leaf, value, device)
        except (ValueError, KeyError, TypeError) as e:
            self.log.put(("err", f"bad payload on {msg.topic}: {e}"))

    # -- command path ------------------------------------------------------
    @property
    def can_command(self) -> bool:
        return bool(MQTT_CMD_PASSWORD)

    def send_command(self, short: str, verb: str, payload: str) -> None:
        """Publish cmd/<short>/<verb>. Connects the write client on demand."""
        if not self.can_command:
            raise PermissionError("no MQTT_CMD_PASSWORD set -- read-only mode")
        if self.cmd_client is None:
            c = make_client(f"fleet-manager-cmd-{int(time.time())}")
            c.username_pw_set(MQTT_CMD_USER, MQTT_CMD_PASSWORD)
            c.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            c.loop_start()
            self.cmd_client = c
        topic = f"cmd/{short}/{verb}"
        info = self.cmd_client.publish(topic, payload, qos=0)
        info.wait_for_publish(timeout=5)
        self.log.put(("cmd", f"published {topic} -> '{payload}'"))
        # A clean publish only proves the BROKER accepted it. If esp32-field
        # lacks `topic read cmd/#` in the ACL, delivery is silently dropped and
        # this still looks like success. Confirm the effect in telemetry.
        self.log.put(("warn", "publish accepted by broker -- confirm effect in telemetry, not here"))


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------

COLUMNS = (
    ("short", "Board", 70),
    ("device", "Device", 190),
    ("status", "Status", 75),
    ("breaker", "Breaker", 75),
    ("load", "Load est", 75),
    ("va", "Va (V)", 75),
    ("ia", "Ia (A)", 70),
    ("freq", "Hz", 65),
    ("temp", "Xfmr °C", 70),
    ("kw", "kW", 75),
    ("seen", "Last seen", 80),
)


class FleetApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ESP32 Fleet Manager — ICS Grid Substation Lab")
        self.geometry("1180x620")
        self.minsize(900, 480)

        self.model = FleetModel()
        self.logq: queue.Queue = queue.Queue()
        self.mq = FleetMQTT(self.model, self.logq)

        self._build_ui()
        self.mq.start()
        self.after(500, self._tick)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- layout ------------------------------------------------------------
    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=(10, 8))
        top.pack(fill="x")

        self.conn_lbl = ttk.Label(top, text="connecting…", font=("", 10, "bold"))
        self.conn_lbl.pack(side="left")

        mode = "READ-WRITE (supervisory)" if self.mq.can_command else "READ-ONLY"
        self.mode_lbl = ttk.Label(top, text=f"  ·  mode: {mode}")
        self.mode_lbl.pack(side="left")

        ttk.Label(top, text=f"  ·  broker {MQTT_HOST}:{MQTT_PORT}  ·  {TOPIC_ROOT}/#").pack(side="left")

        # fleet table
        mid = ttk.Frame(self, padding=(10, 0))
        mid.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            mid, columns=[c[0] for c in COLUMNS], show="headings", selectmode="browse"
        )
        for key, label, width in COLUMNS:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="center" if key != "device" else "w")
        self.tree.tag_configure("offline", foreground="#888888")
        self.tree.tag_configure("stale", foreground="#b58900")
        self.tree.tag_configure("open", foreground="#cb4b16")
        self.tree.tag_configure("hot", foreground="#dc322f")
        self.tree.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)

        # command panel
        cmd = ttk.LabelFrame(self, text="Supervisory commands", padding=(10, 8))
        cmd.pack(fill="x", padx=10, pady=(8, 0))

        self.btn_open = ttk.Button(cmd, text="Trip breaker (open)", command=lambda: self._breaker("open"))
        self.btn_open.pack(side="left", padx=(0, 6))
        self.btn_close = ttk.Button(cmd, text="Close breaker", command=lambda: self._breaker("close"))
        self.btn_close.pack(side="left", padx=6)

        ttk.Separator(cmd, orient="vertical").pack(side="left", fill="y", padx=12)

        ttk.Label(cmd, text="role:").pack(side="left")
        self.role_var = tk.StringVar(value="grid")
        self.role_box = ttk.Combobox(
            cmd, textvariable=self.role_var, width=12, state="readonly",
            values=("grid", "substation", "water", "bms", "datacenter", "pipeline"),
        )
        self.role_box.pack(side="left", padx=6)
        self.btn_role = ttk.Button(cmd, text="Set role (reboots board)", command=self._set_role)
        self.btn_role.pack(side="left", padx=6)

        if not self.mq.can_command:
            for b in (self.btn_open, self.btn_close, self.btn_role):
                b.state(["disabled"])
            ttk.Label(
                cmd, text="  read-only: set MQTT_CMD_PASSWORD in .env to enable",
                foreground="#888888",
            ).pack(side="left", padx=10)

        # log
        logf = ttk.LabelFrame(self, text="Event log", padding=(6, 4))
        logf.pack(fill="both", padx=10, pady=8)
        self.logbox = tk.Text(logf, height=7, wrap="none", font=("Courier", 9))
        self.logbox.pack(fill="both", expand=True)
        self.logbox.configure(state="disabled")

    # -- helpers -----------------------------------------------------------
    def _selected_short(self) -> str | None:
        sel = self.tree.selection()
        return sel[0] if sel else None

    def _log(self, kind: str, msg: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.logbox.configure(state="normal")
        self.logbox.insert("end", f"{stamp} [{kind:>4}] {msg}\n")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    # -- commands ----------------------------------------------------------
    def _breaker(self, action: str) -> None:
        short = self._selected_short()
        if not short:
            messagebox.showinfo("No board selected", "Select a board in the table first.")
            return
        verb = "TRIP OPEN" if action == "open" else "CLOSE"
        if not messagebox.askyesno(
            "Confirm supervisory command",
            f"{verb} the breaker on feeder {short}?\n\n"
            f"This publishes to cmd/{short}/breaker and changes field-device state.\n"
            f"Opening collapses feeder current and real power while bus voltage holds.",
        ):
            return
        try:
            self.mq.send_command(short, "breaker", action)
        except Exception as e:
            self._log("err", f"command failed: {e}")

    def _set_role(self) -> None:
        short = self._selected_short()
        if not short:
            messagebox.showinfo("No board selected", "Select a board in the table first.")
            return
        role = self.role_var.get()
        if not messagebox.askyesno(
            "Confirm role change",
            f"Set role='{role}' on board {short}?\n\n"
            f"The board persists this to NVS and REBOOTS immediately.\n\n"
            f"NOTE: FW 1.0.0-grid stores the role but only implements grid physics. "
            f"A non-grid role will persist and survive reboot, but the board keeps "
            f"publishing the grid model to grid/{short}/#. See ADR-0002.",
        ):
            return
        try:
            self.mq.send_command(short, "role", role)
        except Exception as e:
            self._log("err", f"command failed: {e}")

    # -- refresh loop ------------------------------------------------------
    def _tick(self) -> None:
        while not self.logq.empty():
            kind, msg = self.logq.get_nowait()
            self._log(kind, msg)

        self.conn_lbl.configure(
            text="● connected" if self.mq.connected else "● disconnected",
            foreground="#2aa198" if self.mq.connected else "#dc322f",
        )

        boards = self.model.snapshot()
        existing = set(self.tree.get_children())
        for b in boards:
            load = b.load_est
            temp = b.tags.get("transformer_temp")
            vals = (
                b.short,
                b.device or "-",
                b.status,
                b.breaker,
                f"{load:.2f}" if load is not None else "-",
                f"{b.tags['voltage_a']:.0f}" if "voltage_a" in b.tags else "-",
                f"{b.tags['current_a']:.0f}" if "current_a" in b.tags else "-",
                f"{b.tags['frequency']:.2f}" if "frequency" in b.tags else "-",
                f"{temp:.1f}" if temp is not None else "-",
                f"{b.tags['real_power_kw']:.0f}" if "real_power_kw" in b.tags else "-",
                f"{time.time() - b.last_seen:.0f}s" if b.last_seen else "-",
            )
            tags = []
            if b.status == "OFFLINE":
                tags.append("offline")
            elif b.status == "STALE":
                tags.append("stale")
            if b.breaker == "OPEN":
                tags.append("open")
            if temp is not None and temp >= XFMR_WARN_C:
                tags.append("hot")

            if b.short in existing:
                self.tree.item(b.short, values=vals, tags=tags)
            else:
                self.tree.insert("", "end", iid=b.short, values=vals, tags=tags)
                self._log("ok", f"discovered feeder {b.short} ({b.device or 'unnamed'})")

        self.after(1000, self._tick)

    def _on_close(self) -> None:
        self.mq.stop()
        self.destroy()


if __name__ == "__main__":
    if not MQTT_PASSWORD:
        raise SystemExit(
            "MQTT_PASSWORD is not set.\n"
            "Copy .env.example to .env and fill it in from Vaultwarden, "
            "or export MQTT_PASSWORD in your shell."
        )
    FleetApp().mainloop()
