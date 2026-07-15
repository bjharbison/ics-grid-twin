# ADR-0010: Grafana never received the env vars its own provisioning file expects

**Status:** Accepted · **Date:** 2026-07-15

## Context

The Grafana datasource provisioning file
(`infra/grafana/provisioning/datasources/influxdb.yml`) uses Grafana's built-in
`${VAR}` expansion to inject the InfluxDB org, bucket, and token without
hardcoding them:

```yaml
organization: ${INFLUX_ORG}
defaultBucket: ${INFLUX_BUCKET}
secureJsonData:
  token: ${INFLUX_TOKEN}
```

This works by Grafana reading **its own process environment** at container
startup and substituting into the files it reads from
`/etc/grafana/provisioning`. That is a different, later mechanism than
docker-compose's `.env` substitution, which only fills in `${VAR}` references
written directly *inside* `docker-compose.yml` when the file is parsed.

The `grafana` service's `environment:` block set `GF_SECURITY_ADMIN_USER` and
`GF_SECURITY_ADMIN_PASSWORD` — both consumed correctly by compose-level
substitution — but never passed `INFLUX_ORG`, `INFLUX_BUCKET`, or
`INFLUX_TOKEN` into the container itself. The bridge and InfluxDB services were
wired correctly; only Grafana was missed, because compose-level substitution
"working" for the admin credentials masked that a second, container-internal
substitution step was needed for the datasource.

**Effect on a fresh clone:** the datasource would provision with an empty or
literal `${INFLUX_ORG}` string as its org. Since the org name is case- and
space-sensitive (`ICS Lab`), every panel in the fleet dashboard would fail to
query, on the very first `docker compose --profile sim up` a new user ran —
directly contradicting the "runs with zero hardware" claim the whole no-hardware
path is built on.

Caught by re-auditing the compose file end-to-end after being asked directly
whether a fresh clone would actually come up clean, rather than by anyone
hitting it.

## Decision

Pass `INFLUX_ORG`, `INFLUX_BUCKET`, and `INFLUX_TOKEN` into the `grafana`
service's `environment:` block, identically to how the bridge and InfluxDB
services already receive them. Grafana's internal expansion now has something
to expand.

## Consequence

`docker compose --profile sim up` now produces a working Grafana datasource on
a genuinely fresh clone with no manual dashboard configuration. The general
lesson: a config value flowing correctly through one substitution layer
(compose file → container env) does not mean it reaches a *second* layer
(container env → an application's own internal provisioning) if that
application does its own separate expansion. Any container that provisions
itself from `${VAR}`-style files needs to be checked as its own hop, not
assumed to inherit whatever `.env` already covers elsewhere in the stack.
