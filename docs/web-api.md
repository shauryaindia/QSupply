# Optional local web API

The FastAPI service exposes existing QSupply CVRP functionality to a local
browser application. FastAPI is an optional adapter: importing or using the
core `qsupply` package does not require web dependencies.

## Install and run

From the repository root, install the optional service dependencies and run:

```sh
python3 -m pip install -r requirements-web.txt
PYTHONPATH=src python3 -m uvicorn qsupply.api.app:app --reload --host 127.0.0.1 --port 8000
```

The interactive API documentation is available at `http://127.0.0.1:8000/docs`.
The OpenAPI document is served at `http://127.0.0.1:8000/openapi.json`.

## API surface

- `GET /api/v1/health` reports service availability.
- `GET /api/v1/capabilities` reports implemented solvers and explicitly
  unavailable or unverified capabilities.
- `GET /api/v1/instances` lists deterministic synthetic CVRP examples.
- `GET /api/v1/networks/demo` returns validated synthetic India–Europe network
  data, including a corridor closure scenario. It does not optimize or recover
  routes.
- `GET /api/v1/global/network`, `/shipments`, `/shipments/{id}`, and
  `/scenarios` expose the separate geocoded synthetic global demonstration.
- `GET /api/v1/global/demos` lists six deterministic business examples with
  shipment IDs, constraints, candidate alternatives and optional built-in
  disruption scenarios.
- `POST /api/v1/global/routes` generates and validates bounded candidate routes
  for a shipment under an optional disruption scenario.
- `POST /api/v1/global/route-intelligence` returns route rankings, metric deltas
  against the selected baseline, deadline/capacity indicators, mode-level
  synthetic carbon and deterministic rule-based explanations. It does not call
  an LLM.
- Route-intelligence and optimization requests accept optional `shipment_ids`
  to define the capacity-sharing assignment scope. The legacy optimization
  default remains the original `EXP-104` and `EXP-205` pair; the dashboard sends
  the selected demo's shipment IDs explicitly. The bounded assignment supports
  at most eight selected shipments.
- `GET /api/v1/global/scenarios`, `POST /api/v1/global/scenarios`,
  `GET /api/v1/global/scenarios/{scenario_id}`, and
  `DELETE /api/v1/global/scenarios/{scenario_id}` list, persist, retrieve, and
  delete custom synthetic network overlays. Saved scenarios combine closures,
  unavailable locations, reduced capacities, freight and transit-time
  multipliers, and additive transit delays. Completed runs retain their own
  immutable scenario snapshot after a scenario is deleted.
- `POST /api/v1/global/optimizations` persists and evaluates a baseline
  shipment-to-route assignment and, when requested, a disruption recovery
  assignment. `GET /api/v1/global/optimizations` and
  `/optimizations/{id}` return the persisted run history/result.
- `GET /api/v1/global/optimizations/{run_id}/shipments/{shipment_id}/position`
  returns deterministic simulated movement at the supplied elapsed time.
- `GET /api/v1/global/optimizations/{run_id}/report.csv` exports the saved
  baseline/recovery metrics and selected route legs as a CSV report.
- `GET /api/v1/global/optimizations/{run_id}/report.pdf` exports a PDF summary
  from the persisted result.
- `POST /api/v1/global/optimizations/{run_id}/questions` answers supported
  questions using a deterministic provider and returns the numerical source
  facts. No LLM is configured.
- `POST /api/v1/runs` queues a real QSupply nearest-neighbour,
  nearest-neighbour + 2-opt, or exact CVRP solver run.
- `GET /api/v1/runs` and `GET /api/v1/runs/{id}` return persistent run
  history and results.

The exact solver and exact comparison are limited to 10 customers. Results are
validated against the source CVRP problem before persistence. Run timing covers
the selected solver; optional exact-reference timing is reported separately.
If `DATABASE_URL` is set, the API uses PostgreSQL through Psycopg. Render's
`postgres://` URL scheme is normalized internally to `postgresql://`. When
`DATABASE_URL` is absent, local development uses SQLite at
`~/.qsupply/runs.sqlite3`; set `QSUPPLY_RUNS_DB` to choose another path.

Schema changes are applied transactionally at first store use and tracked in
`schema_migrations`. Version 1 creates the original run-history schema;
version 2 adds a private request-input JSON column; version 3 creates global
optimization run-history storage; version 4 adds persisted custom global
scenarios. Existing run records are preserved. Future
database changes should add a new numbered migration rather than editing
applied versions. Selecting PostgreSQL does not copy historical rows from a
previous SQLite file; export/import that history separately before a production
cutover if those records must remain available.

For Render, install `requirements-web.txt` and set `DATABASE_URL` on the
backend service to the database's internal connection URL. Keep that value in
Render's environment configuration; do not commit it or print it. Since both
services are in Oregon, the internal URL uses Render's private network. The
application opens and closes one connection per database operation; this keeps
transactions isolated and avoids cross-thread connection sharing. A pooled
connection strategy may be appropriate if API traffic grows.

The optional `QSUPPLY_TEST_POSTGRES_URL` enables real PostgreSQL integration
tests. Tests never use `DATABASE_URL` as a test target. Without that explicit
test variable, PostgreSQL integration coverage is skipped; SQLite migration,
transaction and concurrency behavior still runs in the test suite.

Install `requirements-web-test.txt` to run the API integration tests. This adds
the optional API test dependencies without making them runtime requirements of
the core package.

This local API uses FastAPI's in-process background task mechanism. It is
appropriate for small local examples, not a durable distributed job queue.

The global demonstration uses a curated synthetic graph of 74 locations and
122 directed links, nine built-in what-if overlays, six demo workflows, and
synthetic routes, prices, transit times, capacity
and emissions. Global candidate paths are bounded and deterministic, and the
shipment assignment search is exact only over those generated candidates and
is limited to small batches. Resilience is a normalized route exposure metric;
recovery feasibility is separately checked against scenario capacities.
Movement positions are deterministic interpolations along supplied synthetic
route geometry and do not represent live tracking. The map uses OpenStreetMap
tiles with visible attribution; the public tile service is for ordinary
interactive use and has no production service guarantee.
