# Scraping / Collection Policy

APIx treats **ethical collection as a design feature**, not an afterthought.
This document states the rules, and — since `v0.2` — points at the code that
*enforces* them rather than merely recommending them.

The collection engine lives in [`backend/app/collect/`](../backend/app/collect).
It is a real, running scraper: scheduled background sweeps, live HTTP, parsing,
normalization, quality gating, SQLite persistence, an API and a dashboard screen.
What it does not do is evade a site's access controls.

---

## Hard rules

1. **Do not circumvent access controls.** No CAPTCHA-solving, no auth bypass, no
   "bot-detector" evasion, no circumvention of robots.txt or terms of service.
2. **If a source blocks automated collection:** `STOP_AND_BACKOFF`. Recording a
   blocked collection as a healthy run is prohibited.
3. **Prefer authorized channels**: licensed feeds, public APIs, permissioned
   access, manually supplied datasets, or deterministic mock/synthetic data.
4. **Rate limit & throttle.** Respect per-source rate limits and backoff
   schedules.
5. **Never claim disabled/live incorrectly.** The Collection Monitor explicitly
   disambiguates `healthy`, `degraded`, `blocked`, `disabled` and `ready`. A
   source that is stopped is never shown as live.

## Where each rule is enforced

| Rule | Enforcement point |
| --- | --- |
| No evasion | [`headers.NOT_IMPLEMENTED`](../backend/app/collect/headers.py) — a written blocklist of techniques, surfaced in the API (`GET /api/collect/policy`) and on the Live Feed screen |
| robots.txt first | [`robots.RobotsGate`](../backend/app/collect/robots.py) — every generic adapter must pass it; **fails closed** if robots.txt cannot be read (`APIX_ROBOTS_FAIL_CLOSED=1`) |
| Host containment | `AllowListTransport` — a generic adapter can only contact hosts on its own configured allow-list |
| Throttling | `Politeness` in [`transport.py`](../backend/app/collect/transport.py) — per-host minimum gap, `Crawl-delay` adoption, `Retry-After` honouring, exponential backoff, and a hard per-sweep request ceiling |
| Stop and back off | `CollectionService._sweep_source` — a `blocked`/`robots_denied` error breaks the sweep immediately; the circuit breaker then opens and **no requests are issued at all** until the cooldown expires |
| Honest failure | `store.collection_runs` — blocked/failed/partial runs are rows in the run log, rendered on the Collection Monitor and Live Feed screens |
| Bot-wall handling | `SourceAdapter._guard_against_denial` — a 200 response that is actually an interstitial is classified `blocked` and stopped, never solved |
| No silent data loss | `normalize` + `store` — every response body is archived verbatim before parsing, so a rejected observation is still auditable |
| Decide before you fetch | [`preflight.py`](../backend/app/collect/preflight.py) — `python -m app.collect.preflight <url>` / `GET /api/collect/preflight?url=` reports the verdict, the crawl-delay and the request volume a sweep would generate, plus the ToS/redistribution checklist a machine cannot settle |

The per-sweep request ceiling is deliberately **not** counted as a source
failure (`kind="ceiling"`): if we stop ourselves for politeness, that must not
open a circuit breaker against a source that did nothing wrong.

## Case study: why Google Flights is not a source

The obvious request for this project is "scrape the Google Flights results page
for this `tfs=` URL and store it". That is the one thing this engine is built not
to do, for three independent reasons — any one of them is disqualifying:

1. **Terms of service.** Google's terms prohibit automated access to the service
   except through the interfaces Google provides, and Google Flights publishes no
   such interface for fare data. Scraping `google.com/travel/flights` therefore
   requires defeating the bot defences sitting in front of it.
2. **It is technically an evasion project, not a parsing project.** That page is
   JS-rendered and gated. Any implementation that *works* does so via a headless
   browser with fingerprint and header spoofing, proxy/UA rotation, consent-cookie
   reuse or CAPTCHA handling — precisely the list in `NOT_IMPLEMENTED`. The
   request-headers module implements content negotiation (`Accept`,
   `Accept-Language`, `Accept-Encoding`, conditional `ETag` requests, a
   self-identifying `User-Agent` with a contact address) and nothing whose purpose
   is to make a robot look like a person, because such headers have no function
   for a data endpoint other than deception.
3. **The data would be unusable for the actual purpose.** A CPI-augmentation
   series has to survive an auditor asking "where did this number come from, and
   can you re-derive it?". A price observed once, secretly, from a consumer page
   whose markup and licensing can change or send a legal letter at any time has no
   attestation path. Compare a licensed feed where every observation carries a
   `raw_payload_reference` into an archived response.

For a hackathon prototype the practical risk is immediate as well: the sandboxes
and CI runners used for these builds get IP-blocked mid-demo, which is the worst
possible moment to discover your data path was never durable.

**What to do instead.** The engine is designed so that the *same* pipeline runs on
data you are allowed to have:

| Option | Status | Notes |
| --- | --- | --- |
| Amadeus for Developers (self-service) | implemented — `APIX_COLLECTOR_SOURCES=amadeus` | Official REST API, free test tier, real `Flight Offers Search` shapes. Test-environment prices are sample data; production credentials return live offers with the same response model. |
| Licensed OTA / airline feed under contract | implemented via config | `APIX_COLLECTOR_SOURCES=http_json` + `APIX_LIVE_HTTP_JSON_*` |
| A public page whose ToS permit automation | implemented via config | `APIX_COLLECTOR_SOURCES=http_html` + `APIX_LIVE_HTTP_HTML_*`; robots gate enforced |
| Manually supplied datasets (DGCA, airline tariff sheets, MoSPI drops) | supported | Load into the `observations` table, or add a small adapter |
| Authorized offline capture (this repo) | default — `APIX_COLLECTOR_SOURCES=fixture` | In-process OTA-shaped payloads; exercises fetch → parse → normalize → quality → store → index → API with no network at all |
| Authorized offline **page scrape** | `APIX_COLLECTOR_SOURCES=fixture_html` | Renders an HTML fare table and scrapes it with `HttpHtmlAdapter` (selectors, `₹4,899.00` money strings, `@data-offer-id` attributes, blank sold-out price cells). No API anywhere in the path — this is the scraping code path itself, runnable offline |

A `tfs=`-style booking URL is still useful here — as a **query specification**: it
encodes origin, destination and date, which is exactly what `collect.Query`
carries. Reading that URL out of a link to build a search is fine; requesting a
Google results page is not.

## Adapter contract

Every source adapter implements a consistent interface:

```python
class SourceAdapter:
    async def collect(self, query: Query) -> RawBatch:
        """Fetch offers. Raise CollectionError(kind=...) on any failure."""

    async def health_check(self) -> HealthStatus:
        ...
```

`CollectionError.kind` is the vocabulary the monitor is built from:
`blocked`, `robots_denied`, `rate_limited`, `ceiling`, `network`, `timeout`,
`parse`. All adapter output is normalized into the canonical fare model (see
[Data Dictionary](DATA_DICTIONARY.md)) by
[`normalize.normalize_offer`](../backend/app/collect/normalize.py).

## Plugging in a real scraper

1. Implement `collect()` returning `RawBatch(offers=[RawOffer(payload=…)])` for a
   route + date + lead time. `HttpJsonAdapter` covers "give me a URL template and
   a field map"; subclass only for genuinely odd shapes (see `AmadeusAdapter`).
2. Map its fields into the canonical observation model via `FieldMap` — unknown
   source fields are preserved inside `payload`, so nothing is silently dropped.
3. Emit `raw_payload_reference` pointing to the stored raw payload. The store does
   this for you if you let it archive the response (the default).
4. Register the source with an appropriate `status` and `compliance`, and declare
   `requires_robots_gate = True` unless the channel is authorized.
5. Respect the dedup/quality rules so downstream indexes remain sound. Do not
   special-case the index: if a fare is excluded, the reason must be in
   `exclusion_reason`.

The index, quality and API layers do not care whether data came from a live
scraper or the synthetic generator — they consume the same canonical shape. That
is why the dashboard's data-source toggle can flip *every* screen at once.

## Configuration reference

| Variable | Default | Meaning |
| --- | --- | --- |
| `APIX_COLLECTOR_ENABLED` | `1` | Master switch for the background loop |
| `APIX_COLLECTOR_SOURCES` | `fixture` | Comma list: `fixture`, `amadeus`, `http_json`, `http_html` |
| `APIX_SWEEP_INTERVAL_SECONDS` | `900` | Scheduled sweep period |
| `APIX_SWEEP_ROUTES` / `APIX_SWEEP_LEAD_TIMES` | all basket / `1,7,30` | Sweep scope |
| `APIX_MAX_REQUESTS_PER_SWEEP` | `120` | Hard politeness ceiling per sweep |
| `APIX_MIN_REQUEST_GAP_SECONDS` | `2.0` | Minimum gap per host |
| `APIX_MAX_RETRIES` / `APIX_BACKOFF_BASE_SECONDS` | `3` / `2.0` | Retry budget |
| `APIX_ROBOTS_FAIL_CLOSED` | `1` | Refuse to collect if robots.txt is unreadable |
| `APIX_USER_AGENT` | `APIxResearchBot/0.2 (+url; contact:…)` | Honest identification — put a real contact here |
| `APIX_CB_THRESHOLD` / `APIX_CB_COOLDOWN_SECONDS` | `3` / `1800` | Circuit breaker |
| `APIX_DATA_MODE` | unset | Pin `demo`/`live`, overriding the dashboard toggle |
| `AMADEUS_CLIENT_ID` / `AMADEUS_CLIENT_SECRET` | unset | Credentials for the permissioned API |
