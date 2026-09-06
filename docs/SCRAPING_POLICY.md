# Scraping / Collection Policy

APIx treats **ethical collection as a design feature**, not an afterthought.

## What the adapter contract requires

Every source adapter implements a consistent interface:

```python
class SourceAdapter:
    def search(self, query: Query) -> list[RawObservation]:
        ...

    def health_check(self) -> HealthStatus:
        ...
```

All source outputs are normalized into the canonical fare model (see
[Data Dictionary](DATA_DICTIONARY.md)).

## Hard rules

1. **Do not circumvent access controls.** No CAPTCHA-solving, no auth bypass,
   no "bot-detector" evasion, no circumvention of robots.txt or terms of
   service.
2. **If a source blocks automated collection:** `STOP_AND_BACKOFF`. Recording a
   blocked collection as a healthy run is prohibited.
3. **Prefer authorized channels**: licensed feeds, public APIs, permissioned
   access, manually supplied datasets, or deterministic mock/synthetic data.
4. **Rate limit & throttle.** Respect per-source rate limits and backoff
   schedules.
5. **Never claim disabled/live incorrectly.** The Collection Monitor explicitly
   disambiguates `healthy`, `degraded`, `disabled` and `ready`. A source that is
   stopped is never shown as live.

## Source compliance in the demo

The demo environment uses:

- **Mock Source** / **Mock OTA A / B / C** / **Mock Airline Direct** — authorized
  synthetic data with `compliance: authorized`.
- **Ixigo** — present as a proof-of-concept adapter footprint but
  `status: disabled` with `compliance: policy_gated`. It emits **no** data and is
  labelled as disabled, so the demo never implies a live connection.
- **Mock OTA D (Planned)** — `status: ready`, configured but not live.

No scraper in this repository implements methods designed to circumvent CAPTCHA,
authentication, access controls, robots restrictions, explicit anti-bot
restrictions or terms-of-service restrictions.

## Plugging in a real scraper

When you provide your scraper program (as noted in the build plan), it should:

1. Implement `search()` returning raw observations for a route+date+lead time.
2. Map its fields into the canonical observation model.
3. Emit `raw_payload_reference` pointing to stored raw payloads.
4. Register the source in `SOURCES` with an appropriate `status` and
   `compliance`.
5. Respect the dedup/quality rules so downstream indexes remain sound.

The index, quality and API layers do not care whether data comes from a live
scraper or the synthetic generator — they consume the same canonical shape.
