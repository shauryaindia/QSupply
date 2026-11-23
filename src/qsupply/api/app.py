"""FastAPI application exposing existing QSupply functionality to the dashboard."""

from pathlib import Path
import csv
from io import StringIO
import json
from time import perf_counter
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from qsupply import (
    MAX_EXACT_CUSTOMERS,
    ExactQUBOSolver,
    ProblemRepresentation,
    QAOAConfig,
    SolverRequest,
    evaluate_business_objective,
    formulate_import_export_qubo,
    synthetic_import_export_problem,
)
from qsupply.backends.registry import (
    DEFAULT_QUANTUM_BACKEND_REGISTRY,
    QuantumBackendRegistry,
    UnknownQuantumBackendError,
)
from qsupply.network.global_demo import (
    global_demo_disruptions,
    global_demo_network,
    global_demo_scenarios,
    global_demo_shipments,
)
from qsupply.network.models import DisruptionScenario
from qsupply.network.planning import ObjectiveWeights, RecoverySearchLimitError, assign_routes
from qsupply.network.route_qubo import (
    MAX_ROUTE_QUBO_VARIABLES,
    RouteAssignmentQUBO,
    RouteBusinessMetrics,
)
from qsupply.network.route_qubo_demo import (
    ROUTE_QUBO_DEMO_SCENARIO,
    build_route_qubo_demo,
)

from .global_service import (
    generate_shipment_routes,
    get_shipment_profile,
    global_network_response,
    movement_for_result,
    run_global_optimization,
    route_intelligence,
    scenario_response,
    get_global_scenario,
    global_demo_response,
    normalize_persisted_global_optimization,
    shipment_response,
    answer_decision_question,
)
from .instances import get_cvrp_instance, list_cvrp_instances, synthetic_network_response
from .run_service import execute_run
from .reporting import global_report_pdf
from .schemas import (
    CapabilitiesResponse,
    CandidateRouteResponse,
    CapabilityStatus,
    HealthResponse,
    GlobalOptimizationListResponse,
    GlobalOptimizationRecord,
    GlobalOptimizationRequest,
    GlobalDemoScenarioResponse,
    GlobalScenarioCreateRequest,
    DecisionQuestionRequest,
    DecisionAnswerResponse,
    GlobalRoutesRequest,
    GlobalShipment,
    InstanceSummary,
    NetworkScenario,
    NetworkResponse,
    QuantumExecutionError,
    QuantumExecutionMetadata,
    QuantumExecutionTimings,
    QuantumQAOARequest,
    QuantumQAOAResponse,
    QuantumBackendCapability,
    QuantumSampleEnergy,
    QuantumSampleFrequency,
    RouteQUBOCandidate,
    ObjectiveWeightsInput,
    RouteQUBOBackendOption,
    RouteQUBOExampleResponse,
    RouteQUBOMetrics,
    RouteQUBORunRequest,
    RouteQUBORunResponse,
    RouteQUBOVariableMapping,
    RunCreateRequest,
    RunListResponse,
    RunRecord,
    RouteIntelligenceRequest,
    RouteIntelligenceResponse,
    ShipmentPositionResponse,
    SolverCapability,
    SolverId,
)
from .storage import create_run_store


def _energy_text(value: object) -> str | None:
    return None if value is None else str(value)


def _route_qubo_variable_mapping(
    formulation: RouteAssignmentQUBO,
) -> list[RouteQUBOVariableMapping]:
    mapped: dict[str, RouteQUBOVariableMapping] = {}
    for (shipment_id, route_id), variable in formulation.route_variables.items():
        mapped[variable] = RouteQUBOVariableMapping(
            variable=variable,
            kind="route_choice",
            shipment_id=shipment_id,
            route_id=route_id,
        )
    for link_id, bits in formulation.slack_variables.items():
        for variable, weight in bits:
            mapped[variable] = RouteQUBOVariableMapping(
                variable=variable,
                kind="capacity_slack",
                link_id=link_id,
                slack_weight=weight,
            )
    return [mapped[name] for name in formulation.variable_order]


def _backend_integration_description(backend: dict[str, object]) -> str:
    description = str(backend["description"])
    version = backend["version"]
    if backend["available"] and version:
        return f"{description} Installed version: {version}."
    if version is not None:
        return (
            f"{description} Detected version: {version}. Install or update "
            f"{backend['dependency_requirements']} to enable this backend."
        )
    return f"{description} Install {backend['dependency_requirements']} to enable this backend."


def create_app(
    database_path: str | Path | None = None,
    *,
    database_url: str | None = None,
    quantum_backend_registry: QuantumBackendRegistry | None = None,
) -> FastAPI:
    app = FastAPI(
        title="QSupply API",
        description="Local dashboard API backed by the existing QSupply Python package.",
        version="0.1.0",
    )
    app.state.run_store = create_run_store(database_path, database_url)
    backend_registry = quantum_backend_registry or DEFAULT_QUANTUM_BACKEND_REGISTRY
    app.state.quantum_backend_registry = backend_registry
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
        backend_capabilities = backend_registry.capabilities()
        integrations = [
            CapabilityStatus(
                id=f"{backend['id']}-qaoa",
                status=backend["status"],
                description=_backend_integration_description(backend),
            )
            for backend in backend_capabilities
        ]
        integrations.append(
            CapabilityStatus(
                id="fujitsu-qarp",
                status="not_configured_or_verified",
                description="No QARP adapter or verified FX700 connection is configured.",
            )
        )
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
                CapabilityStatus(id="qubo-formulation", status="available", description="QUBO energy evaluation, import-export formulation, and a bounded multimodal route-assignment QUBO bridge; no general-purpose QUBO solver."),
                CapabilityStatus(id="cvrp", status="available", description="CVRP model, heuristic, exact solver, and CVRP benchmarks."),
                CapabilityStatus(id="multimodal-network-models", status="available", description="Validated geospatial network, link, shipment, and disruption models."),
                CapabilityStatus(id="multimodal-route-optimization", status="available_demo", description="Bounded candidate-route generation, classical assignment, and a small QUBO/QAOA bridge on labelled synthetic data; no general production optimizer."),
                CapabilityStatus(id="milp", status="unavailable", description="No MILP adapter is implemented."),
            ],
            integrations=integrations,
            exact_cvrp_customer_limit=MAX_EXACT_CUSTOMERS,
            backends=[QuantumBackendCapability(**backend) for backend in backend_capabilities],
        )

    @app.post(
        "/api/v1/quantum/qubo-runs",
        response_model=QuantumQAOAResponse,
        status_code=201,
        tags=["quantum"],
    )
    def run_quantum_qaoa(request: QuantumQAOARequest) -> QuantumQAOAResponse:
        try:
            backend_registration = backend_registry.get(request.backend)
        except UnknownQuantumBackendError as error:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown quantum backend {request.backend!r}.",
            ) from error
        configuration_errors = backend_registration.configuration_errors(
            {
                "depth": request.depth,
                "optimizer": request.optimizer,
                "max_iterations": request.max_iterations,
                "shots": request.shots,
                "random_seed": request.random_seed,
            }
        )
        if configuration_errors:
            raise HTTPException(
                status_code=422,
                detail="Unsupported configuration for selected backend: "
                + "; ".join(configuration_errors),
            )
        if not backend_registration.is_available():
            raise HTTPException(
                status_code=503,
                detail=(
                    f"{backend_registration.optional_dependency} is an optional dependency unavailable "
                    "in this API environment; "
                    f"install {backend_registration.dependency_requirements}."
                ),
            )
        problem = synthetic_import_export_problem()
        formulation = formulate_import_export_qubo(problem)
        config = QAOAConfig(
            depth=request.depth,
            optimizer=request.optimizer,
            max_iterations=request.max_iterations,
            shots=request.shots,
            random_seed=request.random_seed,
        )
        solver_request = SolverRequest(
            qubo=formulation.qubo,
            constant_offset=formulation.offset,
            representation=ProblemRepresentation.ISING,
            validator=formulation.check_feasibility,
            decoder=formulation.decode,
            business_objective=lambda selections: evaluate_business_objective(
                problem, selections
            ),
            random_seed=request.random_seed,
            configuration={"example": request.example},
        )
        solver = backend_registration.solver_factory(config)
        result = solver.solve(solver_request)

        exact_energy = None
        exact_feasible = None
        exact_elapsed = None
        gap = None
        if request.compare_exact:
            exact_result = ExactQUBOSolver().solve(
                SolverRequest(
                    qubo=formulation.qubo,
                    constant_offset=formulation.offset,
                    validator=formulation.check_feasibility,
                    decoder=formulation.decode,
                    business_objective=lambda selections: evaluate_business_objective(
                        problem, selections
                    ),
                )
            )
            exact_energy = exact_result.full_energy
            exact_feasible = exact_result.feasible
            exact_elapsed = exact_result.execution_time_seconds
            if result.full_energy is not None and exact_energy != 0:
                gap = float(
                    (result.full_energy - exact_energy) / abs(exact_energy) * 100
                )

        variables = formulation.qubo.variables
        return QuantumQAOAResponse(
            run_id=result.run_id,
            status=result.status.value,
            backend_name=result.backend_name or backend_registration.name,
            backend_id=request.backend,
            backend_version=result.backend_version,
            algorithm_name=result.algorithm_name or "QAOA",
            algorithm_version=result.algorithm_version or "unknown",
            example=request.example,
            variable_count=len(variables),
            variable_order=list(variables),
            depth=request.depth,
            optimizer=request.optimizer,
            optimizer_iterations=result.optimizer_iterations,
            shots_per_evaluation=request.shots,
            cost_normalization_scale=str(
                result.configuration.get("cost_normalization_scale", "1")
            ),
            final_sample_count=sum(result.sample_frequencies.values()),
            total_sample_count=result.sample_count,
            random_seed=request.random_seed,
            best_binary_assignment=(
                dict(result.best_binary_assignment)
                if result.best_binary_assignment is not None
                else None
            ),
            best_spin_assignment=(
                dict(result.best_spin_assignment)
                if result.best_spin_assignment is not None
                else None
            ),
            best_sample_frequency=result.best_sample_frequency,
            sample_frequencies=[
                QuantumSampleFrequency(bitstring="".join(map(str, bits)), count=count)
                for bits, count in sorted(result.sample_frequencies.items())
            ],
            sample_energies=[
                QuantumSampleEnergy(
                    bitstring="".join(map(str, bits)),
                    count=record.frequency,
                    qubo_energy=str(record.qubo_energy),
                    full_energy=str(record.full_energy),
                    ising_energy=str(record.ising_energy),
                )
                for bits, record in sorted(result.sample_energies.items())
            ],
            execution_metadata=(
                QuantumExecutionMetadata(
                    backend_id=result.execution_metadata.backend_id,
                    backend_name=result.execution_metadata.backend_name,
                    backend_version=result.execution_metadata.backend_version,
                    execution_mode=result.execution_metadata.execution_mode.value,
                    timing_scope=result.execution_metadata.timing_scope,
                    timings=QuantumExecutionTimings(
                        submission_seconds=result.execution_metadata.timings.submission_seconds,
                        queue_seconds=result.execution_metadata.timings.queue_seconds,
                        remote_execution_seconds=result.execution_metadata.timings.remote_execution_seconds,
                        result_retrieval_seconds=result.execution_metadata.timings.result_retrieval_seconds,
                    ),
                    attributes=dict(result.execution_metadata.attributes),
                )
                if result.execution_metadata is not None
                else None
            ),
            error_details=(
                QuantumExecutionError(
                    category=result.error_details.category.value,
                    message=result.error_details.message,
                    exception_type=result.error_details.exception_type,
                )
                if result.error_details is not None
                else None
            ),
            qubo_energy=_energy_text(result.qubo_energy),
            full_energy=_energy_text(result.full_energy),
            ising_energy=_energy_text(result.ising_energy),
            average_sampled_energy=_energy_text(result.average_sampled_energy),
            exact_reference_energy=_energy_text(exact_energy),
            exact_reference_feasible=exact_feasible,
            exact_reference_time_seconds=exact_elapsed,
            energy_gap_percent=gap,
            feasible=result.feasible,
            feasible_sample_rate=result.feasible_sample_rate,
            decoded_solution=(
                dict(result.decoded_solution)
                if result.decoded_solution is not None
                else None
            ),
            business_objective=_energy_text(result.business_objective),
            optimization_time_seconds=result.optimization_time_seconds,
            circuit_execution_time_seconds=result.circuit_execution_time_seconds,
            elapsed_seconds=result.execution_time_seconds,
            error=result.error,
        )

    @app.get(
        "/api/v1/quantum/route-assignment/example",
        response_model=RouteQUBOExampleResponse,
        tags=["quantum", "global-optimization"],
    )
    def route_assignment_qubo_example() -> RouteQUBOExampleResponse:
        try:
            formulation, _ = build_route_qubo_demo()
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        methods = [
            {"id": "exact-qubo", "name": "Exact QUBO enumeration", "available": True,
             "description": "Exhaustive minimum of the penalized route-assignment QUBO."},
            {"id": "classical-assignment", "name": "Classical exact assignment", "available": True,
             "description": "Capacity-aware enumeration over the same generated candidate routes."},
        ]
        methods.extend(
            {
                "id": capability["id"],
                "name": capability["name"],
                "available": capability["available"],
                "description": capability["description"],
            }
            for capability in backend_registry.capabilities()
        )
        profiles = {profile.request.id: profile for profile in formulation.profiles}
        return RouteQUBOExampleResponse(
            scenario_id=ROUTE_QUBO_DEMO_SCENARIO.id,
            scenario_description=(
                "Synthetic restriction: Shanghai port-road access capacity is reduced "
                "from 30 to 3 load units."
            ),
            shipment_ids=list(profiles),
            candidates={
                shipment_id: [
                    RouteQUBOCandidate(
                        id=route.id,
                        modes=[mode.value for mode in route.modes],
                        link_ids=[leg.link_id for leg in route.legs],
                        freight_cost=str(route.freight_cost),
                        transit_time=str(route.transit_time),
                        carbon_kg=str(route.carbon_kg),
                        resilience_exposure=str(route.resilience_exposure),
                    )
                    for route in routes
                ]
                for shipment_id, routes in formulation.candidates.items()
            },
            variable_order=list(formulation.variable_order),
            variable_kinds=dict(formulation.variable_kinds),
            variable_mapping=_route_qubo_variable_mapping(formulation),
            decision_variable_count=formulation.decision_variable_count,
            slack_variable_count=formulation.slack_variable_count,
            variable_count=formulation.variable_count,
            variable_limit=MAX_ROUTE_QUBO_VARIABLES,
            qubo_coefficients=[
                (left, right, str(value))
                for (left, right), value in formulation.qubo.coefficients.items()
            ],
            qubo_offset=str(formulation.offset),
            infeasibility_penalty=str(formulation.penalty),
            normalization_references={
                "cost": str(formulation.normalization_references.cost),
                "delivery_time": str(formulation.normalization_references.delivery_time),
                "carbon": str(formulation.normalization_references.carbon),
                "resilience": str(formulation.normalization_references.resilience),
            },
            weights=ObjectiveWeightsInput(),
            available_methods=[RouteQUBOBackendOption(**method) for method in methods],
        )

    @app.post(
        "/api/v1/quantum/route-assignment/runs",
        response_model=RouteQUBORunResponse,
        status_code=201,
        tags=["quantum", "global-optimization"],
    )
    def run_route_assignment_qubo(request: RouteQUBORunRequest) -> RouteQUBORunResponse:
        weights = ObjectiveWeights(**request.weights.model_dump())
        try:
            formulation, comparison = build_route_qubo_demo(weights)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        exact_started = perf_counter()
        exact_result = ExactQUBOSolver().solve(
            formulation.solver_request(ProblemRepresentation.QUBO)
        )
        exact_seconds = perf_counter() - exact_started
        exact_routes = (
            dict(exact_result.decoded_solution)
            if exact_result.feasible and exact_result.decoded_solution is not None
            else None
        )
        exact_objective = exact_result.business_objective

        backend_id = request.backend
        backend_name = backend_id
        execution_mode = "local_classical"
        timing_scope = "solver execution, including its own validation callbacks"
        selected_assignment = None
        selected_result = None
        selected_elapsed = 0.0
        selected_depth = None
        selected_shots = None
        selected_optimizer = None
        selected_iterations = None

        if backend_id == "exact-qubo":
            selected_result = exact_result
            selected_assignment = exact_result.best_binary_assignment
            backend_name = exact_result.solver_name
            selected_elapsed = exact_result.execution_time_seconds
            timing_scope = "exhaustive QUBO enumeration and solver validation callbacks"
        elif backend_id == "classical-assignment":
            classical_started = perf_counter()
            classical = assign_routes(
                formulation.network,
                formulation.profiles,
                comparison.recovery_candidates,
                formulation.weights,
                formulation.normalization_references,
                formulation.scenario,
            )
            selected_elapsed = perf_counter() - classical_started
            if classical is not None:
                selected_assignment = formulation.encode_plan(
                    {shipment_id: route.id for shipment_id, route in classical.routes.items()}
                )
            backend_name = "Capacity-aware exact candidate assignment"
            timing_scope = "candidate assignment search and independent plan validation"
        else:
            try:
                registration = backend_registry.get(backend_id)
            except UnknownQuantumBackendError as error:
                raise HTTPException(
                    status_code=422, detail=f"Unknown quantum backend {backend_id!r}."
                ) from error
            configuration = {
                "depth": request.depth,
                "optimizer": request.optimizer,
                "max_iterations": request.max_iterations,
                "shots": request.shots,
                "random_seed": request.random_seed,
            }
            errors = registration.configuration_errors(configuration)
            if errors:
                raise HTTPException(
                    status_code=422,
                    detail="Unsupported configuration for selected backend: " + "; ".join(errors),
                )
            if not registration.is_available():
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"{registration.optional_dependency} is unavailable; install "
                        f"{registration.dependency_requirements} in the API environment."
                    ),
                )
            qaoa_config = QAOAConfig(
                depth=request.depth,
                optimizer=request.optimizer,
                max_iterations=request.max_iterations,
                shots=request.shots,
                random_seed=request.random_seed,
            )
            selected_result = registration.solver_factory(qaoa_config).solve(
                formulation.solver_request(ProblemRepresentation.ISING)
            )
            selected_assignment = selected_result.best_binary_assignment
            selected_elapsed = selected_result.execution_time_seconds
            backend_name = registration.name
            execution_mode = registration.execution_mode.value
            timing_scope = (
                "whole QAOA solver call including optimization, sample calls, energy "
                "rescoring and domain validation; see execution_metadata for backend sample-call scope"
            )
            selected_depth = request.depth
            selected_shots = request.shots
            selected_optimizer = request.optimizer
            selected_iterations = selected_result.optimizer_iterations

        evaluation = (
            formulation.evaluate_assignment(selected_assignment)
            if selected_assignment is not None
            else None
        )
        if selected_result is not None and evaluation is not None:
            if selected_result.full_energy != evaluation.full_penalized_energy:
                try:
                    agrees = abs(float(selected_result.full_energy) - float(evaluation.full_penalized_energy)) <= 1e-9
                except (TypeError, ValueError, OverflowError):
                    agrees = False
                if not agrees:
                    raise HTTPException(status_code=500, detail="solver energy does not reconcile with the original route QUBO")

        selected_objective = (
            None if evaluation is None or evaluation.business_metrics is None
            else evaluation.business_metrics.weighted_objective
        )
        exact_feasible = exact_result.feasible is True
        objective_gap = None
        if (
            selected_objective is not None
            and exact_objective is not None
            and exact_objective != 0
        ):
            objective_gap = float(
                (selected_objective - exact_objective) / abs(exact_objective) * 100
            )
        selected_routes = (
            dict(evaluation.feasibility.selected_routes)
            if evaluation is not None and evaluation.feasibility.feasible
            else None
        )
        route_lookup = {
            profile.request.id: {route.id: route for route in formulation.candidates[profile.request.id]}
            for profile in formulation.profiles
        }
        route_details = {
            shipment_id: RouteQUBOCandidate(
                id=route_id,
                modes=[mode.value for mode in route_lookup[shipment_id][route_id].modes],
                link_ids=[leg.link_id for leg in route_lookup[shipment_id][route_id].legs],
                freight_cost=str(route_lookup[shipment_id][route_id].freight_cost),
                transit_time=str(route_lookup[shipment_id][route_id].transit_time),
                carbon_kg=str(route_lookup[shipment_id][route_id].carbon_kg),
                resilience_exposure=str(route_lookup[shipment_id][route_id].resilience_exposure),
            )
            for shipment_id, route_id in (selected_routes or {}).items()
        }
        metrics = evaluation.business_metrics if evaluation is not None else None
        classical_reference_objective = None
        if comparison.recovery is not None:
            classical_reference_objective = formulation.evaluate_business_objective(
                {
                    shipment_id: route.id
                    for shipment_id, route in comparison.recovery.routes.items()
                }
            ).weighted_objective

        def metric_response(value: RouteBusinessMetrics | None) -> RouteQUBOMetrics | None:
            if value is None:
                return None
            return RouteQUBOMetrics(
                freight_cost=str(value.freight_cost),
                delay_penalty=str(value.delay_penalty),
                total_cost=str(value.total_cost),
                delivery_time=str(value.delivery_time),
                carbon_kg=str(value.carbon_kg),
                resilience_exposure=str(value.resilience_exposure),
                weighted_objective=str(value.weighted_objective),
            )

        return RouteQUBORunResponse(
            run_id=selected_result.run_id if selected_result is not None else str(uuid4()),
            status=(selected_result.status.value if selected_result is not None else "completed"),
            backend_id=backend_id,
            backend_name=backend_name,
            backend_version=(selected_result.backend_version if selected_result is not None else None),
            execution_mode=execution_mode,
            timing_scope=timing_scope,
            elapsed_seconds=selected_elapsed,
            optimization_time_seconds=(
                selected_result.optimization_time_seconds
                if selected_result is not None and selected_depth is not None
                else None
            ),
            circuit_execution_time_seconds=(
                selected_result.circuit_execution_time_seconds
                if selected_result is not None and selected_depth is not None
                else None
            ),
            scenario_id=ROUTE_QUBO_DEMO_SCENARIO.id,
            shipment_ids=[profile.request.id for profile in formulation.profiles],
            variable_count=formulation.variable_count,
            decision_variable_count=formulation.decision_variable_count,
            slack_variable_count=formulation.slack_variable_count,
            depth=selected_depth,
            shots=selected_shots,
            random_seed=request.random_seed if selected_depth is not None else None,
            optimizer=selected_optimizer,
            optimizer_iterations=selected_iterations,
            execution_metadata=(
                QuantumExecutionMetadata(
                    backend_id=selected_result.execution_metadata.backend_id,
                    backend_name=selected_result.execution_metadata.backend_name,
                    backend_version=selected_result.execution_metadata.backend_version,
                    execution_mode=selected_result.execution_metadata.execution_mode.value,
                    timing_scope=selected_result.execution_metadata.timing_scope,
                    timings=QuantumExecutionTimings(
                        submission_seconds=selected_result.execution_metadata.timings.submission_seconds,
                        queue_seconds=selected_result.execution_metadata.timings.queue_seconds,
                        remote_execution_seconds=selected_result.execution_metadata.timings.remote_execution_seconds,
                        result_retrieval_seconds=selected_result.execution_metadata.timings.result_retrieval_seconds,
                    ),
                    attributes=dict(selected_result.execution_metadata.attributes),
                )
                if selected_result is not None and selected_result.execution_metadata is not None
                else None
            ),
            error=(selected_result.error if selected_result is not None else None),
            error_category=(
                selected_result.error_details.category.value
                if selected_result is not None and selected_result.error_details is not None
                else None
            ),
            variable_order=list(formulation.variable_order),
            variable_kinds=dict(formulation.variable_kinds),
            variable_mapping=_route_qubo_variable_mapping(formulation),
            qubo_coefficients=[
                (left, right, str(value))
                for (left, right), value in formulation.qubo.coefficients.items()
            ],
            qubo_offset=str(formulation.offset),
            infeasibility_penalty=str(formulation.penalty),
            best_binary_assignment=(dict(selected_assignment) if selected_assignment is not None else None),
            qubo_energy=(str(evaluation.qubo_energy) if evaluation is not None else None),
            full_penalized_energy=(str(evaluation.full_penalized_energy) if evaluation is not None else None),
            ising_energy=(str(selected_result.ising_energy) if selected_result is not None and selected_result.ising_energy is not None else None),
            feasible=(evaluation.feasibility.feasible if evaluation is not None else None),
            feasibility_violations=(list(evaluation.feasibility.violations) if evaluation is not None else []),
            decoded_routes=selected_routes,
            route_details=route_details,
            capacity_usage=(dict(evaluation.feasibility.capacity_usage) if evaluation is not None else {}),
            capacity_utilization=(dict(evaluation.feasibility.capacity_utilization) if evaluation is not None else {}),
            business_metrics=metric_response(metrics),
            objective_gap_percent=objective_gap,
            exact_reference_objective=(str(exact_objective) if exact_objective is not None else None),
            exact_reference_qubo_energy=str(exact_result.qubo_energy),
            exact_reference_full_energy=str(exact_result.full_energy),
            exact_reference_feasible=exact_feasible,
            exact_reference_routes=exact_routes,
            exact_reference_seconds=exact_seconds,
            classical_reference_objective=(
                str(classical_reference_objective)
                if classical_reference_objective is not None else None
            ),
            classical_reference_feasible=comparison.recovery_feasible,
            classical_reference_routes=(
                {
                    shipment_id: route.id
                    for shipment_id, route in comparison.recovery.routes.items()
                }
                if comparison.recovery is not None else None
            ),
            reference_scope="exact optimum over the explicitly generated three candidate routes per shipment under fixed baseline normalization",
        )

    @app.get("/api/v1/instances", response_model=list[InstanceSummary], tags=["cvrp"])
    def instances() -> list[InstanceSummary]:
        return list_cvrp_instances()

    @app.get("/api/v1/networks/demo", response_model=NetworkResponse, tags=["network"])
    def demo_network() -> NetworkResponse:
        return synthetic_network_response()

    @app.get("/api/v1/global/network", response_model=NetworkResponse, tags=["global-network"])
    def global_network() -> NetworkResponse:
        return global_network_response(app.state.run_store)

    @app.get("/api/v1/global/shipments", response_model=list[GlobalShipment], tags=["global-network"])
    def global_shipments() -> list[GlobalShipment]:
        return [shipment_response(profile) for profile in global_demo_shipments()]

    @app.get(
        "/api/v1/global/demos",
        response_model=list[GlobalDemoScenarioResponse],
        tags=["global-network"],
    )
    def global_demos() -> list[GlobalDemoScenarioResponse]:
        return [GlobalDemoScenarioResponse.model_validate(global_demo_response(demo)) for demo in global_demo_scenarios()]

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
        return global_network_response(app.state.run_store).scenarios

    @app.post(
        "/api/v1/global/scenarios",
        response_model=NetworkScenario,
        status_code=201,
        tags=["global-network"],
    )
    def create_global_scenario(request: GlobalScenarioCreateRequest) -> NetworkScenario:
        scenario_id = f"custom-{uuid4()}"
        try:
            scenario = DisruptionScenario(
                id=scenario_id,
                closed_link_ids=frozenset(request.closed_link_ids),
                unavailable_location_ids=frozenset(request.unavailable_location_ids),
                capacity_overrides=request.capacity_overrides,
                cost_multipliers=request.cost_multipliers,
                transit_time_multipliers=request.transit_time_multipliers,
                transit_time_additions=request.transit_time_additions,
            )
            scenario.validate_for(global_demo_network())
        except (TypeError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        stored = app.state.run_store.create_global_scenario(
            scenario_id,
            request.name.strip(),
            request.description.strip(),
            {
                "closed_link_ids": sorted(scenario.closed_link_ids),
                "unavailable_location_ids": sorted(scenario.unavailable_location_ids),
                "capacity_overrides": dict(scenario.capacity_overrides),
                "cost_multipliers": dict(scenario.cost_multipliers),
                "transit_time_multipliers": dict(scenario.transit_time_multipliers),
                "transit_time_additions": dict(scenario.transit_time_additions),
            },
        )
        return scenario_response(
            scenario,
            name=stored["name"],
            description=stored["description"],
            custom=True,
            created_at=stored["created_at"],
        )

    @app.get(
        "/api/v1/global/scenarios/{scenario_id}",
        response_model=NetworkScenario,
        tags=["global-network"],
    )
    def get_global_scenario_detail(scenario_id: str) -> NetworkScenario:
        if any(scenario.id == scenario_id for scenario in global_demo_disruptions()):
            scenario = next(item for item in global_network_response(app.state.run_store).scenarios if item.id == scenario_id)
            return scenario
        stored = app.state.run_store.get_global_scenario(scenario_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="Scenario was not found")
        scenario = get_global_scenario(scenario_id, app.state.run_store)
        assert scenario is not None
        return scenario_response(
            scenario,
            name=stored["name"],
            description=stored["description"],
            custom=True,
            created_at=stored["created_at"],
        )

    @app.delete("/api/v1/global/scenarios/{scenario_id}", status_code=204, tags=["global-network"])
    def delete_global_scenario(scenario_id: str) -> Response:
        if any(scenario.id == scenario_id for scenario in global_demo_disruptions()):
            raise HTTPException(status_code=409, detail="The built-in scenario cannot be deleted")
        if not app.state.run_store.delete_global_scenario(scenario_id):
            raise HTTPException(status_code=404, detail="Scenario was not found")
        return Response(status_code=204)

    @app.post(
        "/api/v1/global/routes",
        response_model=list[CandidateRouteResponse],
        tags=["global-network"],
    )
    def global_routes(request: GlobalRoutesRequest) -> list[CandidateRouteResponse]:
        try:
            return generate_shipment_routes(
                request.shipment_id, request.scenario_id, request.max_routes, app.state.run_store
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Shipment or scenario was not found") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post(
        "/api/v1/global/route-intelligence",
        response_model=RouteIntelligenceResponse,
        tags=["global-optimization"],
    )
    def global_route_intelligence(
        request: RouteIntelligenceRequest,
    ) -> RouteIntelligenceResponse:
        try:
            return route_intelligence(
                request.shipment_id,
                request.scenario_id,
                request.weights.model_dump(),
                request.max_routes,
                app.state.run_store,
                request.shipment_ids,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Shipment or scenario was not found") from error
        except (ValueError, RecoverySearchLimitError) as error:
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
        if request.scenario_id is not None and get_global_scenario(request.scenario_id, app.state.run_store) is None:
            raise HTTPException(status_code=404, detail="Disruption scenario was not found")
        app.state.run_store.create_global_optimization(
            run_id, request.scenario_id, weights
        )
        try:
            result = run_global_optimization(
                run_id, request.scenario_id, weights, request.max_routes,
                app.state.run_store, request.shipment_ids,
            )
            app.state.run_store.complete_global_optimization(run_id, result)
        except KeyError as error:
            app.state.run_store.fail_global_optimization(run_id, "Unknown shipment or disruption scenario")
            raise HTTPException(status_code=404, detail="Shipment or disruption scenario was not found") from error
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
                GlobalOptimizationRecord.model_validate(normalize_persisted_global_optimization(item))
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
        return GlobalOptimizationRecord.model_validate(normalize_persisted_global_optimization(record))

    @app.get(
        "/api/v1/global/optimizations/{run_id}/report.csv",
        response_class=Response,
        tags=["global-optimization"],
    )
    def global_optimization_report(run_id: str) -> Response:
        record = app.state.run_store.get_global_optimization(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Optimization run was not found")
        normalize_persisted_global_optimization(record)
        if record["status"] != "completed" or record["result"] is None:
            raise HTTPException(status_code=409, detail="Completed optimization result is not available")
        result = record["result"]
        stream = StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(["QSupply synthetic route comparison report"])
        writer.writerow(["Run ID", record["id"]])
        writer.writerow(["Created at", record["created_at"]])
        writer.writerow(["Scenario", record["scenario_id"] or "baseline network"])
        writer.writerow(["Method", result["algorithm"]])
        writer.writerow(["Optimality scope", result["optimality_scope"]])
        writer.writerow(["Scenario snapshot", json.dumps(result.get("scenario_snapshot"), sort_keys=True)])
        writer.writerow(["Objective weights", json.dumps(record["weights"], sort_keys=True)])
        writer.writerow(["Normalization references", json.dumps(result["normalization_references"], sort_keys=True)])
        writer.writerow([])
        writer.writerow(["Plan", "Feasible", "Total cost", "Delay penalty", "Delivery time (days)", "Carbon estimate (kgCO2e)", "Resilience exposure", "Weighted score"])
        for plan_name in ("baseline", "recovery"):
            plan = result.get(plan_name)
            if not plan:
                continue
            metrics = plan["metrics"]
            writer.writerow([
                plan_name,
                "yes" if plan_name == "baseline" or result["recovery_feasible"] else "no",
                metrics["total_cost"],
                metrics["delay_penalty"],
                metrics["delivery_time"],
                metrics["carbon_kg"],
                metrics["resilience_exposure"],
                metrics["weighted_objective"],
            ])
            if plan_name == "recovery":
                baseline_metrics = result["baseline"]["metrics"]
                writer.writerow(["Scenario delta vs baseline", "Metric", "Absolute difference"])
                for metric, unit in (
                    ("total_cost", record.get("cost_unit", "cost units")),
                    ("delivery_time", "summed shipment-days"),
                    ("carbon_kg", "kgCO2e estimate"),
                ):
                    before = baseline_metrics[metric]
                    after = metrics[metric]
                    difference = after - before
                    percent = (100 * difference / before) if before else None
                    writer.writerow(["recovery", f"{metric} ({unit})", difference, "percent change", percent])
            writer.writerow([])
            writer.writerow([f"{plan_name} route alternatives"])
            writer.writerow(["Shipment", "Route", "Selected", "Modes", "Distance km", "Transit days", "Freight cost", "Carbon estimate kgCO2e", "Resilience exposure", "Transfers"])
            for shipment_id, selected_route in plan["routes"].items():
                options = [selected_route, *plan["alternatives"].get(shipment_id, [])]
                for route in options:
                    writer.writerow([
                        shipment_id,
                        route["id"],
                        "yes" if route["id"] == selected_route["id"] else "no",
                        " / ".join(route["modes"]),
                        route["distance_km"],
                        route["transit_time"],
                        route["freight_cost"],
                        route["carbon_kg"],
                        route["resilience_exposure"],
                        route["transfer_count"],
                    ])
            writer.writerow([])
            writer.writerow([f"{plan_name} selected route legs"])
            writer.writerow(["Shipment", "Route", "Leg", "Mode", "Distance km", "Transit days", "Freight cost", "Carbon estimate kgCO2e", "Link capacity", "Resilience exposure"])
            for shipment_id, route in plan["routes"].items():
                for leg in route["legs"]:
                    writer.writerow([
                        shipment_id,
                        route["id"],
                        leg["link_id"],
                        leg["mode"],
                        leg["distance_km"],
                        leg["transit_time"],
                        leg["freight_cost"],
                        leg["carbon_kg"],
                        leg["capacity"],
                        leg.get("resilience_exposure")
                        if leg.get("resilience_exposure") is not None
                        else "unknown",
                    ])
        writer.writerow([])
        writer.writerow(["Assumptions", "Synthetic costs, transit times, capacities, emissions factors and disruption inputs; rule-based route analysis; no customs, handling, inventory or reliability model."])
        return Response(
            content=stream.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="qsupply-{run_id}-report.csv"'},
        )

    @app.get(
        "/api/v1/global/optimizations/{run_id}/report.pdf",
        response_class=Response,
        tags=["global-optimization"],
    )
    def global_optimization_pdf_report(run_id: str) -> Response:
        record = app.state.run_store.get_global_optimization(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Optimization run was not found")
        normalize_persisted_global_optimization(record)
        if record["status"] != "completed" or record["result"] is None:
            raise HTTPException(status_code=409, detail="Completed optimization result is not available")
        return Response(
            content=global_report_pdf(record),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="qsupply-{run_id}-report.pdf"'},
        )

    @app.post(
        "/api/v1/global/optimizations/{run_id}/questions",
        response_model=DecisionAnswerResponse,
        tags=["decision-intelligence"],
    )
    def ask_about_optimization(
        run_id: str, request: DecisionQuestionRequest
    ) -> DecisionAnswerResponse:
        record = app.state.run_store.get_global_optimization(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Optimization run was not found")
        normalize_persisted_global_optimization(record)
        if record["status"] != "completed" or record["result"] is None:
            raise HTTPException(status_code=409, detail="Completed optimization result is not available")
        try:
            return DecisionAnswerResponse.model_validate(
                answer_decision_question(
                    record,
                    request.shipment_id,
                    request.question,
                    request.route_id,
                )
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Shipment or route was not found in this run") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

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
        normalize_persisted_global_optimization(record)
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
