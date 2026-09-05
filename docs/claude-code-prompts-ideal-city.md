# Claude Code Prompts: "Ideal City Finder" (Spain)

## How to use this document

Each section below is a self-contained prompt you can feed to Claude Code
sequentially (one at a time, waiting for the previous result). Order matters —
each prompt builds on artifacts from the previous one.

Before starting: initialize an empty git repo, create a root `.env` with the
required keys (see `.env.example`), and add `.env` to `.gitignore`.

---

## Prompt 1 — Project init and data model

```
Create a monorepo structure for a "find the ideal city" search app for Spain:

backend/   — Python 3.13, FastAPI, SQLAlchemy 2.0 (async), Alembic for migrations
frontend/  — React (Vite), TypeScript
infra/     — docker-compose for Postgres+PostGIS and Redis

Backend stack:
- FastAPI + Pydantic v2
- asyncpg + SQLAlchemy async
- PostGIS extension for geo queries
- Redis + arq (lightweight Celery alternative) for background jobs
- python-jose (or similar) for JWT auth

Create docker-compose.yml with services:
- postgres (image postgis/postgis:16-3.4)
- redis (image redis:7-alpine)

Create SQLAlchemy models in backend/app/models.py:

1. City
   - id, name, province, population
   - location: Geography(Point, srid=4326)  # via GeoAlchemy2
   - source: string ("INE")

2. Airport
   - id, name, iata_code
   - location: Geography(Point, srid=4326)
   (static reference list of Spanish AENA airports, ~46 records)

3. PoiCache
   - id, query (text), city_id (FK), found (bool)
   - distance_km (numeric, nullable)
   - raw_response (JSONB)
   - fetched_at (timestamptz, default now())
   - UNIQUE index on (query, city_id)

4. WeatherNormals
   - id, city_id (FK, nullable — null means "national average")
   - avg_sunny_days_year (numeric)
   - source (string: "AEMET" or "OpenMeteo")
   - fetched_at

5. RentPriceIndex
   - id, city_id (FK, nullable) or province (string, if data is province-level only)
   - price_per_sqm (numeric)
   - period (string, e.g. "2026-08")
   - source (string: "idealista_index" or "INE")
   - fetched_at

6. SearchRun
   - id (UUID, not a serial int — the frontend polls by this id)
   - user_id (FK -> users, see Prompt 2)
   - user_query (text) — original text as typed by the user
   - language (string, "en" or "ru") — UI language the query/result should be
     rendered in
   - parsed_criteria (JSONB) — result of the OpenAI structured output step
   - tolerance (numeric) — user-configured error margin
   - status (enum: pending, running, done, failed)
   - compared_to_run_id (FK -> SearchRun, nullable) — optional link to a
     previous run this one should be diffed against (see Prompt 9)
   - created_at, completed_at

7. SearchResult
   - id, run_id (FK -> SearchRun), city_id (FK -> City)
   - overall_confidence (numeric)
   - criteria_breakdown (JSONB) — per-criterion confidence + raw values
     (needed for frontend tooltips and for client-side confidence recompute
     when the tolerance slider moves, without a new backend request)

Set up Alembic and generate the first migration.

Do not implement criteria business logic in this step — only project
structure, models, migrations, and docker-compose. Verify that
`docker compose up -d` brings up Postgres with PostGIS enabled and that the
migration applies cleanly.
```

---

## Prompt 2 — Authentication (2 users from .env)

```
Implement simple authentication for the app. There is no user-management UI
and no user table with passwords in the database — exactly two accounts are
defined via environment variables:

AUTH_USER_1_USERNAME=
AUTH_USER_1_PASSWORD=
AUTH_USER_2_USERNAME=
AUTH_USER_2_PASSWORD=
JWT_SECRET_KEY=
JWT_EXPIRE_MINUTES=1440

Backend (backend/app/services/auth.py):
- POST /api/auth/login — accepts { username, password }, checks credentials
  against the two env-configured accounts (compare passwords using a
  constant-time comparison, e.g. secrets.compare_digest — do not store
  passwords hashed for this MVP since they only ever live in .env, but do not
  log them either), returns a JWT access token on success.
- Add a FastAPI dependency `get_current_user` that validates the JWT from the
  Authorization: Bearer header and rejects the request with 401 otherwise.
- Protect all /api/search* endpoints with this dependency.
- Store the numeric/string identifier of which of the two env users made a
  given SearchRun (users.id can simply be "user1"/"user2" derived from which
  env credential pair matched — no separate users table is required for just
  two static accounts, but document this decision in a comment).

Frontend:
- A simple login screen (username + password fields) shown when no valid
  token is present.
- Store the JWT in memory / a secure cookie (not localStorage — this app may
  later run inside contexts where localStorage is unreliable; use an
  httpOnly cookie set by the backend on login, or in-memory state with a
  refresh-on-reload login prompt — pick one approach and document it).
- Attach the token to all API requests; on 401, redirect back to the login
  screen.

Write a test for the login endpoint: correct credentials for user 1 and user
2 both succeed; wrong password fails with 401; malformed JWT on a protected
endpoint fails with 401.
```

---

## Prompt 3 — Reference data: Spanish cities and airports

```
Add a one-off seeding script: backend/app/scripts/seed_reference_data.py

1. Load Spanish municipalities (City table):
   Source — open INE (Instituto Nacional de Estadística) data, or a
   Nominatim/GeoNames dataset with coordinates and population for Spanish
   municipalities. If there is no single reliable CSV source with guaranteed
   uptime, have the script read a local CSV file
   (backend/app/data/municipios_es.csv, to be supplied separately) with
   columns: name, province, population, lat, lon. Make the upsert keyed on
   (name, province) so the script is idempotent.

2. Load airports (Airport table):
   Hardcode the static list of Spain's commercial airports (AENA network,
   ~46 entries) directly in code as a list of dicts (name, iata_code, lat,
   lon) — this data essentially never changes, no API call needed. Use an
   accurate, current list of major and regional Spanish airports.

Add a CLI command (typer or argparse) to run the seeding:
   python -m app.scripts.seed_reference_data --all
```

---

## Prompt 4 — OpenAI structured outputs: criteria parsing

```
Create backend/app/services/criteria_parser.py, which turns free-form user
text into a structured list of search criteria via the OpenAI API
(Structured Outputs / function calling; check current OpenAI docs for the
recommended model at implementation time).

Define Pydantic models for the criteria:

class PoiProximityCriterion(BaseModel):
    type: Literal["poi_proximity"]
    poi_query: str          # e.g. "Conservatorio Profesional de Música"
    radius_km: float
    min_count: int = 1

class AirportProximityCriterion(BaseModel):
    type: Literal["airport_proximity"]
    radius_km: float

class SunnyDaysCriterion(BaseModel):
    type: Literal["sunny_days_above_average"]
    # no parameters — always compared against the Spain-wide national
    # average, computed by a separate service (see Prompt 7)

class RentPriceCriterion(BaseModel):
    type: Literal["rent_price_per_sqm"]
    comparison: Literal["lt", "lte", "gt", "gte"]
    value: float             # euros per square meter

ParsedCriteria = list[
    PoiProximityCriterion | AirportProximityCriterion |
    SunnyDaysCriterion | RentPriceCriterion
]

Use OpenAI Structured Outputs (response_format with json_schema, strict=True)
generated from these Pydantic models — do NOT rely on an unstructured text
prompt without a schema.

The system prompt must explicitly instruct the model that:
- the search country is always fixed to Spain, never suggest other countries
- if a criterion in the user's text does not fit any known type
  (poi_proximity / airport_proximity / sunny_days_above_average /
  rent_price_per_sqm), it must be returned as type="unsupported" with an
  original_text field, rather than forced into an existing type
- numeric values (km, euros) must be extracted literally from the text, not
  guessed or rounded
- the function must accept input in either English or Russian (the app
  supports both UI languages — see Prompt 10) and parse criteria correctly
  regardless of which language the user typed in

Write a unit test using the example from the spec:
"find cities in Spain where within a 20 km radius there is definitely a
Conservatorio de Musica (Basico and Profesional levels), there are 2 or more
private schools, there is an airport within 100 km, more sunny days than the
Spain average, and average rental housing cost no more than 10 euros per
square meter"

Expected test result — a list of 5 criteria: 2 × poi_proximity (conservatory
radius=20, min_count=1; private schools radius=20, min_count=2), 1 ×
airport_proximity (radius=100), 1 × sunny_days_above_average, 1 ×
rent_price_per_sqm (comparison="lte", value=10).

Mock the OpenAI API call in the test (no real network request in unit tests).
```

---

## Prompt 5 — Candidate city selection strategy

```
Create backend/app/services/candidate_selector.py.

Rationale: instead of querying Google Places for all ~8000 Spanish
municipalities, first narrow down the candidate list:

1. Function get_candidate_cities(session, parsed_criteria, min_population=None) -> list[City]
   - If any poi_proximity criterion implies urban infrastructure
     (conservatory, private schools), filter out cities with
     population < 5000 by default (make the threshold a configurable
     constant, not a magic number without an explanatory comment).
   - If there are no infrastructure-related criteria at all, do not apply
     the population filter.

2. Function filter_by_airport_proximity(session, cities, radius_km) -> list[City]
   - Use PostGIS ST_DWithin between City.location and Airport.location in a
     single SQL query (do not loop distance calculations in Python).
   - Also return the actual distance to the nearest airport for each city
     (needed later for confidence calculation with tolerance).

Write an integration test against a real (test) Postgres+PostGIS database:
create 3 test cities and 1 test airport, verify the radius filter correctly
places cities inside/outside the allowed zone.
```

---

## Prompt 6 — Google Places integration for POI criteria

```
Create backend/app/services/google_places.py — a wrapper around the Google
Places API (New) Text Search.

Function:
async def find_poi_near_city(city: City, poi_query: str, radius_km: float) -> PoiSearchResult

- First check PoiCache for the (poi_query, city.id) pair — if the entry is
  fresher than 30 days, return the cached result without calling Google API.
- If no cache hit, run Text Search with locationBias set to the city's
  coordinates and radius_km * 1000 (meters).
- For each result found, compute the actual distance to the city center
  (Haversine, or via PostGIS — pick whichever is simpler to integrate
  without an extra DB round trip for a single calculation).
- Store the result in PoiCache (found, distance_km, raw_response).
- Return: { found: bool, count: int, nearest_distance_km: float | None }

For the "private schools" criterion (min_count=2), note that Google Places
type=school does not reliably distinguish public vs. private schools. Add a
TODO comment and a stub function cross_reference_with_ministerio_educacion(),
which should eventually cross-check against the open Ministerio de Educación
registry (data.gob.es, Registro Estatal de Centros Docentes, field
"titularidad"). For this iteration, filtering by the presence of
"privado"/"colegio privado" in the Google result's name/type is an acceptable
temporary approximation — but explicitly mark it as such in a code comment
and in a confidence_note field on the result.

Add rate limiting (e.g. via asyncio.Semaphore) to avoid hitting Google Places
API quotas when processing many cities in parallel.
```

---

## Prompt 7 — Weather: sunny days (AEMET / Open-Meteo)

```
Create backend/app/services/weather.py.

Preferred source: AEMET OpenData API (Spain's official meteorological
agency, requires a free API key from opendata.aemet.es) — climate normals
per weather station. If AEMET integration turns out too complex for an MVP
(station-specific response format, mapping stations to cities), fall back to
the Open-Meteo Climate API (open-meteo.com, no key required, global
coverage, has archival sunshine-duration data).

Functions:
1. async def get_national_average_sunny_days() -> float
   — average yearly sunny days across Spain as a whole. Cache in
   WeatherNormals with city_id=NULL representing "national average" (or a
   separate flag column is_national_average — your choice, document the
   decision in the docstring).

2. async def get_city_sunny_days(city: City) -> float
   — for a specific city, via the nearest weather station (AEMET) or
   directly by coordinates (Open-Meteo is not station-bound, works by
   coordinates — simpler for an MVP, recommend starting here).

Cache both results with a 30-day TTL (climate normals do not change often,
no need to hit the API on every user search).

The sunny_days_above_average criterion is satisfied when
get_city_sunny_days(city) > get_national_average_sunny_days() — no tolerance
needed here, it's a binary criterion (either above average or not), unlike
distance-based criteria.
```

---

## Prompt 8 — Rent price index (aggregated Idealista statistics)

```
Create backend/app/services/rent_index.py.

IMPORTANT: do NOT scrape individual Idealista listings and do NOT hit
undocumented listing-site endpoints. Only use Idealista's publicly published
aggregated price reports/indices (pages like "Precio de la vivienda en
[city]" showing price per m², which Idealista publishes as open statistics
for general public consumption, requiring no login or API key) — this is a
fundamentally different kind of access than automated harvesting of listing
data.

Implement:
1. async def fetch_rent_index(city_or_province: str) -> RentPriceIndexResult
   — retrieves the current price per m² for a city/province.
   - If no data exists for a specific city (Idealista does not publish an
     index for every one of Spain's ~8000 municipalities), fall back to the
     province level.
   - Cache in RentPriceIndex with a 30-day TTL (the index updates monthly at
     most).
   - Respect the report page's robots.txt; if it disallows automated access,
     switch to INE (Instituto Nacional de Estadística — open housing-price
     statistics by province, explicitly allowed for programmatic access) as
     the primary source instead of Idealista, controlled via an environment
     variable RENT_DATA_SOURCE=idealista_index|ine.

2. Record in RentPriceIndex.source exactly which source a given city's value
   came from — needed to show data provenance in the UI.

If, after research, neither source turns out to be reliably automatable, do
not attempt to bypass site protections; instead return an explicit error
stating that the rent_price_per_sqm criterion is temporarily unavailable for
city X, and lower the overall confidence with a clear "data unavailable"
note rather than silently excluding the city from results.
```

---

## Prompt 9 — Confidence scoring, orchestration, and run comparison

```
Create backend/app/services/confidence.py and
backend/app/services/search_orchestrator.py.

confidence.py:

def criterion_confidence(actual_value: float, threshold: float, tolerance: float) -> float:
    """
    1.0 — criterion fully satisfied (actual <= threshold)
    0.0 — criterion failed even with tolerance (actual >= threshold + tolerance)
    linear decay between threshold and threshold + tolerance
    """
    if tolerance <= 0:
        return 1.0 if actual_value <= threshold else 0.0
    if actual_value <= threshold:
        return 1.0
    if actual_value >= threshold + tolerance:
        return 0.0
    return 1.0 - (actual_value - threshold) / tolerance

def overall_confidence(criterion_scores: dict[str, float], mode: Literal["min", "weighted_avg"] = "min",
                        weights: dict[str, float] | None = None) -> float:
    """
    mode="min" — "weakest link": overall score = minimum across criteria
                 (matches phrasing like "must have X")
    mode="weighted_avg" — weighted average, for less strict scenarios
    """
    ...

search_orchestrator.py:

async def run_search(run_id: UUID, session) -> None:
    Orchestrates the full pipeline for one SearchRun:
    1. Load SearchRun.parsed_criteria and tolerance
    2. Get candidates via candidate_selector.get_candidate_cities()
    3. For each city, in parallel (asyncio.gather with concurrency limited
       via a Semaphore, e.g. 10 concurrent cities), call the handler for
       each criterion:
       - poi_proximity -> google_places.find_poi_near_city()
       - airport_proximity -> use the distance from candidate_selector
       - sunny_days_above_average -> weather.get_city_sunny_days() vs
         weather.get_national_average_sunny_days()
       - rent_price_per_sqm -> rent_index.fetch_rent_index()
    4. For each criterion compute criterion_confidence() using run.tolerance
       (for criteria without a natural "distance", like rent_price_per_sqm
       with comparison="lte", treat value+tolerance as the upper bound of
       the linear decay, analogous to radii)
    5. Compute overall_confidence (mode="min" by default)
    6. Store a SearchResult per city with criteria_breakdown (raw values +
       per-criterion confidence — the frontend needs this for tooltips and
       for recomputing confidence when the tolerance slider moves)
    7. Update SearchRun.status = "done", completed_at = now()

    If any single city's criterion handler errors out, do not fail the whole
    run — mark that criterion as unavailable for that city (see Prompt 8)
    and continue with the rest.

    COMPARISON WITH A PREVIOUS RUN:
    If SearchRun.compared_to_run_id is set, after step 6 compute a diff
    against the referenced run's SearchResults:
    - cities present in both runs: delta = new.overall_confidence -
      old.overall_confidence (and per-criterion deltas from
      criteria_breakdown)
    - cities present only in the new run ("newly appeared")
    - cities present only in the old run ("dropped out")
    Store this diff in a new field SearchRun.comparison_summary (JSONB):
    { added_cities: [...], removed_cities: [...],
      confidence_deltas: { city_id: delta, ... } }

Register run_search as an arq task (backend/app/worker.py).

Create FastAPI endpoints in backend/app/api/search.py (all behind the auth
dependency from Prompt 2):
- POST /api/search — accepts { query: str, tolerance: float,
  compare_to_run_id: UUID | None, language: "en" | "ru" }, calls
  criteria_parser, creates a SearchRun tied to the current user, enqueues
  run_search via arq, returns { run_id }
- GET /api/search/{run_id} — returns status and (if done) the list of
  SearchResults with cities, coordinates, overall_confidence,
  criteria_breakdown, and comparison_summary if applicable
- GET /api/search/history — returns the current user's past SearchRuns
  (id, user_query, created_at, status), most recent first, for the history/
  comparison picker in the UI
```

---

## Prompt 10 — Backend i18n (English / Russian)

```
Add bilingual support (English and Russian) to backend-generated text:

1. Store a translation dictionary for fixed labels the backend produces —
   criterion type names, status messages, error messages (e.g. "data
   unavailable for this city", "invalid credentials") — as a small JSON or
   Python dict keyed by locale: backend/app/i18n/strings.py, with "en" and
   "ru" entries for every key.

2. Every relevant endpoint should accept a language parameter (either an
   explicit `language` field in the request body, as used in POST
   /api/search, or an `Accept-Language` header for endpoints without a
   body) and return user-facing strings (error messages, status labels) in
   that language. Do NOT translate proper nouns — city names, province
   names, and the user's own free-text query stay as-is.

3. Criterion type identifiers themselves (e.g. "poi_proximity") remain
   fixed English enum values in the JSON API — they are not translated.
   Only human-readable labels derived from them are localized, and that
   localization can happen on the frontend (see Prompt 11) using the same
   key set, to avoid duplicating translation strings in two places. Decide
   and document in a code comment: backend translates only error/status
   messages, frontend translates all UI copy and criterion labels via its
   own i18n dictionary keyed by the same criterion `type` values the
   backend returns.
```

---

## Prompt 11 — Frontend: map, table, i18n, login, and run history

```
In frontend/ (React + TypeScript + Vite) implement:

1. LoginScreen — username + password fields, calls POST /api/auth/login,
   stores the resulting session per the approach chosen in Prompt 2, and
   redirects to the main app on success. Shown whenever there is no valid
   session.

2. Internationalization — use react-i18next with two locale files,
   frontend/src/locales/en.json and frontend/src/locales/ru.json, covering
   all UI copy: form labels, buttons, table column headers, criterion type
   labels (poi_proximity, airport_proximity, sunny_days_above_average,
   rent_price_per_sqm → human-readable labels in both languages), status
   messages, and error messages. Add a language switcher (EN/RU toggle) in
   the header, persisted in local component state or a cookie (not
   localStorage per the earlier no-localStorage constraint for this app;
   a simple cookie is fine here since it holds no secret). The
   `language` field sent to POST /api/search should follow the current UI
   language.

3. SearchForm — a text input for the user's query (accepting either English
   or Russian text — the backend criteria parser handles both, see Prompt
   4), a tolerance slider, and a "Compare to previous run" dropdown
   populated from GET /api/search/history, letting the user optionally pick
   a prior run to diff against (sent as compare_to_run_id). On submit: POST
   /api/search, then poll GET /api/search/{run_id} every 2 seconds until
   status !== "done".

4. MapView (top half of the screen) — use @react-google-maps/api. One
   marker per result city; marker color/opacity reflects overall_confidence
   (e.g. a yellow-to-green gradient). If a comparison_summary is present,
   visually distinguish newly-added cities (e.g. a distinct marker icon or
   border) from cities present in both runs.

5. CityTable (bottom half of the screen, @tanstack/react-table) — columns:
   city name, province, coordinates, overall_confidence (as a percentage),
   and expandable per-criterion detail rows from criteria_breakdown. When a
   comparison is active, add a delta column showing the confidence change
   versus the compared run (with up/down indicator), and visually flag
   added/removed cities.

6. HistoryPanel — a simple list/sidebar showing past SearchRuns (from GET
   /api/search/history) the current user can click to reopen past results
   or select as the comparison baseline for a new search.

7. Map/table linkage: clicking a table row centers the map on that city's
   marker and highlights it; clicking a marker scrolls to and highlights
   the corresponding table row.

8. Client-side confidence recompute when the tolerance slider moves,
   without a new backend request — reuse the raw values from
   criteria_breakdown (port criterion_confidence to TypeScript, logic
   identical to the backend version from Prompt 9).

Split components into separate files, use React Query
(@tanstack/react-query) for all backend requests instead of manual
useEffect+fetch, and attach the JWT to every request per Prompt 2.
```

---

## Notes for sequential use

- After each prompt, verify that any requested tests pass before moving to
  the next step.
- Prompts 6–8 (Google Places, weather, rent index) are independent of each
  other and can be handed to Claude Code in any order, or even in parallel
  branches.
- Prompt 9 (orchestration + comparison) is the riskiest in scope; if needed,
  split it into two separate prompts — confidence.py with tests first, then
  search_orchestrator.py (including the comparison logic) separately.
- Prompts 10 and 11 (i18n) depend on the criterion type enum values being
  finalized in Prompt 4 — if criterion types change later, both the backend
  and frontend translation dictionaries need updating together.
