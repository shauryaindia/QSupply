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
- `POST /api/v1/runs` queues a real QSupply nearest-neighbour,
  nearest-neighbour + 2-opt, or exact CVRP solver run.
- `GET /api/v1/runs` and `GET /api/v1/runs/{id}` return SQLite-backed run
  history and results.

The exact solver and exact comparison are limited to 10 customers. Results are
validated against the source CVRP problem before persistence. Run timing covers
the selected solver; optional exact-reference timing is reported separately.
The local SQLite database defaults to `~/.qsupply/runs.sqlite3`; set
`QSUPPLY_RUNS_DB` to choose another path.

Install `requirements-web-test.txt` to run the API integration tests. This adds
the optional API test dependencies without making them runtime requirements of
the core package.

This local API uses FastAPI's in-process background task mechanism. It is
appropriate for small local examples, not a durable distributed job queue.
