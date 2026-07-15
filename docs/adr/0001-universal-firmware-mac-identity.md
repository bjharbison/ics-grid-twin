# ADR-0001: One universal binary, MAC-derived identity

**Status:** Accepted · **Date:** 2026-06

## Context

Six ESP32 boards each simulate a different OT field device. The naive approach —
a per-board sketch with hardcoded identity — means six source files to keep in
sync and a USB reflash for every change.

## Decision

Flash **one identical binary** to all boards. Derive identity deterministically
from the chip MAC (`WiFi.macAddress()` → last three bytes → `boardShort`), and
store role in NVS. A MAC-derived offset gives each board natural per-device
variance without any per-board configuration. Bundle ArduinoOTA into the first
USB flash so every subsequent update is wireless.

## Consequences

* No per-board edits; boards are interchangeable and role-swappable at runtime.
* `WiFi.macAddress()` chosen over `esp_read_mac()` after the latter broke across
  an ESP-IDF version bump — the portable call is worth the tiny cost.
* First flash must be USB (OTA handler doesn't exist until this firmware lands);
  documented as a known one-time constraint, not a limitation.
