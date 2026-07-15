# ADR-0006: `board_id` and `device` as separate InfluxDB tags

**Status:** Accepted · **Date:** 2026-07-12

## Context

An early bridge tagged each point with the full MQTT topic path as a single
`source` tag. Per-board Flux queries then required string-slicing the topic in
every query — painful and error-prone, and it made fleet-aggregate queries
(sum across boards, count distinct boards) awkward.

## Decision

The bridge writes two tags: **`board_id`** (the MAC-tail short id) and
**`device`** (the full `grid-substation-<tail>` name), with the tag/field split
`measurement=<role>`, `field=<tag-name>`.

## Consequence

* Fleet aggregate: `group(columns:["board_id"]) |> last() |> group() |> sum()`.
* Per-feeder drilldown: `filter(fn:(r)=> r.board_id == "${board_id}")` — which is
  exactly the dashboard's template-variable pattern.
* Getting tagging right early avoids a historian migration later.
