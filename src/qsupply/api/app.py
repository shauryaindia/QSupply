"""FastAPI application exposing existing QSupply functionality to the dashboard."""

from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from qsupply import MAX_EXACT_CUSTOMERS
from qsupply.network.global_demo import global_demo_shipments
from qsupply.network.planning import RecoverySearchLimitError

from .global_service import (
    generate_shipment_routes,
    get_shipment_profile,
    global_network_response,
    movement_for_result,
    run_global_optimization,
    shipment_response,
)
from .instances import get_cvrp_instance, list_cvrp_instances, synthetic_network_response
from .run_service import execute_run
from .schemas import (
    CapabilitiesResponse,
    CandidateRouteResponse,
    CapabilityStatus,
    HealthResponse,
    GlobalOptimizationListResponse,
    GlobalOptimizationRecord,
    GlobalOptimizationRequest,
    GlobalRoutesRequest,
    GlobalShipment,
    InstanceSummary,
    NetworkScenario,
    NetworkResponse,
    RunCreateRequest,
    RunListResponse,
    RunRecord,
    ShipmentPositionResponse,
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
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "https://qsupply.netlify.app",
            "https://qsupply.macrovisionai.com",
        ],
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

    @app.get("/api/v1/global/network", response_model=NetworkResponse, tags=["global-network"])
    def global_network() -> NetworkResponse:
        return global_network_response()

    @app.get("/api/v1/global/shipments", response_model=list[GlobalShipment], tags=["global-network"])
    def global_shipments() -> list[GlobalShipment]:
        return [shipment_response(profile) for profile in global_demo_shipments()]

    @app.get(
        "/api/v1/global/shipments/{shipment_id}",
        response_model=GlobalShipment,
        tags=["global-network"],
    )
    def global_shipment(shipment_id: str) -> GlobalShipment:
        profile = get_shipment_profile(shipment_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="Shipment was not found")
        return shipment_response(profile)

    @app.get(
        "/api/v1/global/scenarios",
        response_model=list[NetworkScenario],
        tags=["global-network"],
    )
    def global_scenarios() -> list[NetworkScenario]:
        return global_network_response().scenarios

    @app.post(
        "/api/v1/global/routes",
        response_model=list[CandidateRouteResponse],
        tags=["global-network"],
    )
    def global_routes(request: GlobalRoutesRequest) -> list[CandidateRouteResponse]:
        try:
            return generate_shipment_routes(
                request.shipment_id, request.scenario_id, request.max_routes
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Shipment or scenario was not found") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post(
        "/api/v1/global/optimizations",
        response_model=GlobalOptimizationRecord,
        status_code=201,
        tags=["global-optimization"],
    )
    def create_global_optimization(
        request: GlobalOptimizationRequest,
    ) -> GlobalOptimizationRecord:
        run_id = str(uuid4())
        weights = request.weights.model_dump()
        app.state.run_store.create_global_optimization(
            run_id, request.scenario_id, weights
        )
        try:
            result = run_global_optimization(
                run_id, request.scenario_id, weights, request.max_routes
            )
            app.state.run_store.complete_global_optimization(run_id, result)
        except KeyError as error:
            app.state.run_store.fail_global_optimization(run_id, "Unknown disruption scenario")
            raise HTTPException(status_code=404, detail="Disruption scenario was not found") from error
        except (ValueError, RecoverySearchLimitError) as error:
            app.state.run_store.fail_global_optimization(run_id, str(error))
            raise HTTPException(status_code=422, detail=str(error)) from error
        except Exception as error:
            app.state.run_store.fail_global_optimization(run_id, type(error).__name__)
            raise HTTPException(status_code=500, detail="Global optimization failed") from error
        record = app.state.run_store.get_global_optimization(run_id)
        assert record is not None
        return GlobalOptimizationRecord.model_validate(record)

    @app.get(
        "/api/v1/global/optimizations",
        response_model=GlobalOptimizationListResponse,
        tags=["global-optimization"],
    )
    def list_global_optimizations(
        limit: int = Query(default=50, ge=1, le=200),
    ) -> GlobalOptimizationListResponse:
        return GlobalOptimizationListResponse(
            items=[
                GlobalOptimizationRecord.model_validate(item)
                for item in app.state.run_store.list_global_optimizations(limit)
            ]
        )

    @app.get(
        "/api/v1/global/optimizations/{run_id}",
        response_model=GlobalOptimizationRecord,
        tags=["global-optimization"],
    )
    def get_global_optimization(run_id: str) -> GlobalOptimizationRecord:
        record = app.state.run_store.get_global_optimization(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Optimization run was not found")
        return GlobalOptimizationRecord.model_validate(record)

    @app.get(
        "/api/v1/global/optimizations/{run_id}/shipments/{shipment_id}/position",
        response_model=ShipmentPositionResponse,
        tags=["global-optimization"],
    )
    def shipment_position(
        run_id: str,
        shipment_id: str,
        elapsed_time: float = Query(default=0, ge=0),
    ) -> ShipmentPositionResponse:
        record = app.state.run_store.get_global_optimization(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Optimization run was not found")
        if record["status"] != "completed" or record["result"] is None:
            raise HTTPException(status_code=409, detail="Optimization result is not complete")
        try:
            position = movement_for_result(record["result"], shipment_id, elapsed_time)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Shipment was not found") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return ShipmentPositionResponse.model_validate(position)

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
