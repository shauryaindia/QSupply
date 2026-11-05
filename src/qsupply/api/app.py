"""FastAPI application exposing existing QSupply functionality to the dashboard."""

from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from qsupply import MAX_EXACT_CUSTOMERS

from .instances import get_cvrp_instance, list_cvrp_instances, synthetic_network_response
from .run_service import execute_run
from .schemas import (
    CapabilitiesResponse,
    CapabilityStatus,
    HealthResponse,
    InstanceSummary,
    NetworkResponse,
    RunCreateRequest,
    RunListResponse,
    RunRecord,
    SolverCapability,
    SolverId,
)
from .storage import create_run_store


def create_app(
    database_path: str | Path | None = None,
    *,
    database_url: str | None = None,
) -> FastAPI:
    app = FastAPI(
        title="QSupply API",
        description="Local dashboard API backed by the existing QSupply Python package.",
        version="0.1.0",
    )
    app.state.run_store = create_run_store(database_path, database_url)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="q-supply-api")

    @app.get("/api/v1/capabilities", response_model=CapabilitiesResponse, tags=["system"])
    def capabilities() -> CapabilitiesResponse:
        return CapabilitiesResponse(
            solvers=[
                SolverCapability(
                    id=SolverId.NEAREST_NEIGHBOR,
                    name="Nearest Neighbour",
                    description="Deterministic capacity-constrained CVRP construction.",
                ),
                SolverCapability(
                    id=SolverId.NEAREST_NEIGHBOR_TWO_OPT,
                    name="Nearest Neighbour + 2-opt",
                    description="The nearest-neighbour seed followed by route-local 2-opt.",
                ),
                SolverCapability(
                    id=SolverId.EXACT,
                    name="Exact CVRP Solver",
                    exact_customer_limit=MAX_EXACT_CUSTOMERS,
                    description="Held–Karp route costs and exact capacity-aware subset assignment.",
                ),
            ],
            features=[
                CapabilityStatus(id="qubo-formulation", status="available", description="QUBO energy evaluation and import-export QUBO formulation; no general QUBO solver."),
                CapabilityStatus(id="cvrp", status="available", description="CVRP model, heuristic, exact solver, and CVRP benchmarks."),
                CapabilityStatus(id="multimodal-network-models", status="available", description="Validated network, link, shipment, and disruption data models; no multimodal route optimizer yet."),
                CapabilityStatus(id="milp", status="unavailable", description="No MILP adapter is implemented."),
            ],
            integrations=[
                CapabilityStatus(id="qiskit-qaoa", status="not_implemented", description="No Qiskit or QAOA integration is implemented."),
                CapabilityStatus(id="fujitsu-qarp", status="not_configured_or_verified", description="No QARP adapter or verified FX700 connection is configured."),
            ],
            exact_cvrp_customer_limit=MAX_EXACT_CUSTOMERS,
        )

    @app.get("/api/v1/instances", response_model=list[InstanceSummary], tags=["cvrp"])
    def instances() -> list[InstanceSummary]:
        return list_cvrp_instances()

    @app.get("/api/v1/networks/demo", response_model=NetworkResponse, tags=["network"])
    def demo_network() -> NetworkResponse:
        return synthetic_network_response()

    @app.get("/api/v1/runs", response_model=RunListResponse, tags=["runs"])
    def list_runs(limit: int = Query(default=100, ge=1, le=500)) -> RunListResponse:
        return RunListResponse(items=app.state.run_store.list(limit))

    @app.get("/api/v1/runs/{run_id}", response_model=RunRecord, tags=["runs"])
    def get_run(run_id: str) -> RunRecord:
        record = app.state.run_store.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} was not found")
        return record

    @app.post(
        "/api/v1/runs",
        response_model=RunRecord,
        status_code=202,
        tags=["runs"],
        description="Execute one of the implemented CVRP solvers against a labelled synthetic instance.",
    )
    def create_run(request: RunCreateRequest, background_tasks: BackgroundTasks) -> RunRecord:
        try:
            problem = get_cvrp_instance(request.instance_id)
        except KeyError as error:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown CVRP instance {request.instance_id!r}",
            ) from error
        customer_count = len(problem.customer_demands)
        if request.solver is SolverId.EXACT and customer_count > MAX_EXACT_CUSTOMERS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Exact CVRP solver supports at most {MAX_EXACT_CUSTOMERS} customers; "
                    f"instance has {customer_count}"
                ),
            )
        if request.include_exact_reference and customer_count > MAX_EXACT_CUSTOMERS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Exact comparison is unavailable above {MAX_EXACT_CUSTOMERS} customers; "
                    f"instance has {customer_count}"
                ),
            )

        run_id = str(uuid4())
        record = app.state.run_store.create(
            run_id,
            request.instance_id,
            request.solver.value,
            request_payload=request.model_dump(mode="json"),
        )
        background_tasks.add_task(
            execute_run,
            app.state.run_store,
            run_id,
            request.instance_id,
            request.solver,
            request.include_exact_reference,
        )
        return record

    return app


app = create_app()
