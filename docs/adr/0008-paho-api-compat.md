# ADR-0008: paho-mqtt 1.x/2.x compatibility via a client factory

**Status:** Accepted · **Date:** 2026-07-15

## Context

`requirements.txt` pinned `paho-mqtt>=2.0,<3.0`, and all three MQTT clients (the
fleet manager's read client, its command client, and the bridge) were
constructed the 1.x way:

```python
mqtt.Client(client_id="mqtt-bridge")
```

**paho-mqtt 2.0 made `callback_api_version` a required first positional
argument.** Constructing a client without it raises at startup:

```
ValueError: Unsupported callback API version: version 2.0 added a
callback_api_version, see docs/migrations.rst for details
```

So the pinned dependency and the code contradicted each other: a fresh
`pip install -r requirements.txt` followed by `python esp32_fleet.py` would have
crashed before it ever reached the broker. Same for the bridge container, which
builds its dependencies fresh on every `docker compose build`.

Caught during a pre-release read-through, not at runtime — the sandbox this was
authored in had no network to install paho against.

## Decision

Route every client through a factory that requests the VERSION1 callback API
explicitly on paho 2.x and falls back to the bare constructor on 1.x:

```python
try:
    _CALLBACK_V1 = mqtt.CallbackAPIVersion.VERSION1      # paho >= 2.0
except AttributeError:
    _CALLBACK_V1 = None                                  # paho 1.x

def make_client(client_id: str) -> "mqtt.Client":
    if _CALLBACK_V1 is not None:
        return mqtt.Client(_CALLBACK_V1, client_id=client_id)
    return mqtt.Client(client_id=client_id)
```

The existing callbacks are already VERSION1-shaped
(`on_connect(client, userdata, flags, rc)`), so nothing else changes. Pins
widen to `paho-mqtt>=1.6,<3.0` to reflect that both majors genuinely work.

VERSION1 is deprecated but supported throughout paho 2.x. Migrating to VERSION2
(`reason_code.is_failure`, 5-arg `on_disconnect`) is a V2 item — worth doing
deliberately, with a live broker to test against, rather than blind.

## Verification

`verify_physics.py` now asserts, for both the fleet manager and the bridge, that
a `make_client` factory exists, that `CallbackAPIVersion` is handled, and that
**no bare `mqtt.Client(...)` construction survives anywhere**. The fix was
proven against stub modules shaped like each major version — 1.x accepts the
call, 2.x raises without the version argument and succeeds with it.

## Consequence

The repo runs on whatever paho a cloner happens to have. The regression is
locked out by a check rather than a comment — which is the general pattern here:
when a failure is found, add the assertion that would have caught it.
