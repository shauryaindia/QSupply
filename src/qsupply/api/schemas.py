"""Pydantic request and response models for the optional QSupply API."""

from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


class SolverId(str, Enum):
    NEAREST_NEIGHBOR = "nearest-neighbor"
    NEAREST_NEIGHBOR_TWO_OPT = "nearest-neighbor+2-opt"
    EXACT = "exact"


class SolverCapability(BaseModel):
    id: SolverId
    name: str
    available: bool = True
    exact_customer_limit: int | None = None
    description: str


class CapabilityStatus(BaseModel):
    id: str
    status: str
    description: str


class CapabilitiesResponse(BaseModel):
    solvers: list[SolverCapability]
    features: list[CapabilityStatus]
    integrations: list[CapabilityStatus]
    exact_cvrp_customer_limit: int


class RunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instance_id: str = Field(min_length=1)
    solver: SolverId
    include_exact_reference: bool = False


class RunResult(BaseModel):
    instance_id: str
    instance_name: str
    synthetic: bool
    customer_count: int
    solver: SolverId
    routes: dict[str, list[str]]
    feasible: bool
    total_distance: float
    total_distance_exact: str
    elapsed_seconds: float
    initial_distance: float | None = None
    initial_distance_exact: str | None = None
    improvement_percent: float | None = None
    exact_reference_distance: float | None = None
    exact_reference_distance_exact: str | None = None
    exact_reference_elapsed_seconds: float | None = None
    optimality_gap_percent: float | None = None


class RunRecord(BaseModel):
    id: str
    instance_id: str
    solver: SolverId
    status: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: RunResult | None = None
    error: str | None = None


class RunListResponse(BaseModel):
    items: list[RunRecord]


class QuantumQAOARequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    example: Literal["synthetic-import-export"] = "synthetic-import-export"
    depth: StrictInt = Field(default=1, ge=1, le=3)
    optimizer: Literal["spsa", "coordinate"] = "spsa"
    max_iterations: StrictInt = Field(default=5, ge=1, le=25)
    shots: StrictInt = Field(default=128, ge=16, le=2048)
    random_seed: StrictInt = Field(default=2026, ge=0, le=2147483647)
    compare_exact: bool = True


class QuantumSampleFrequency(BaseModel):
    bitstring: str
    count: int


class QuantumQAOAResponse(BaseModel):
    run_id: str
    status: str
    backend_name: str
    backend_version: str | None
    algorithm_name: str
    algorithm_version: str
    example: str
    synthetic: bool = True
    variable_count: int
    variable_order: list[str]
    depth: int
    optimizer: str
    optimizer_iterations: int
    shots_per_evaluation: int
    cost_normalization_scale: str
    final_sample_count: int
    total_sample_count: int
    random_seed: int
    best_binary_assignment: dict[str, int] | None
    best_spin_assignment: dict[str, int] | None
    best_sample_frequency: int | None
    sample_frequencies: list[QuantumSampleFrequency]
    qubo_energy: str | None
    full_energy: str | None
    ising_energy: str | None
    average_sampled_energy: str | None
    exact_reference_energy: str | None
    exact_reference_time_seconds: float | None
    energy_gap_percent: float | None
    feasible: bool | None
    feasible_sample_rate: float | None
    decoded_solution: dict[str, str] | None
    business_objective: str | None
    optimization_time_seconds: float
    circuit_execution_time_seconds: float
    elapsed_seconds: float
    error: str | None = None


class InstanceSummary(BaseModel):
    id: str
    name: str
    customer_count: int
    seed: int
    synthetic: bool = True
    exact_supported: bool


class NetworkNode(BaseModel):
    id: str
    label: str
    kind: str
    country_code: str | None
    country_name: str | None = None
    region: str | None = None
    timezone: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    transfer_modes: list[str] = Field(default_factory=list)


class NetworkLink(BaseModel):
    id: str
    source: str
    target: str
    mode: str
    capacity: int | None
    capacity_unit: str
    fixed_cost: float
    variable_cost_per_quantity_unit: float
    transit_time: float
    carbon_per_quantity_unit: float
    available: bool
    capabilities: list[str]
    distance_km: float | None = None
    geometry: list[tuple[float, float]] = Field(default_factory=list)
    resilience_exposure: float = 0


class NetworkScenario(BaseModel):
    id: str
    name: str = ""
    description: str
    synthetic: bool = True
    custom: bool = False
    created_at: datetime | None = None
    closed_link_ids: list[str]
    unavailable_location_ids: list[str]
    capacity_overrides: dict[str, int]
    cost_multipliers: dict[str, float]
    transit_time_multipliers: dict[str, float]
    transit_time_additions: dict[str, float] = Field(default_factory=dict)


class GlobalScenarioCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    closed_link_ids: list[str] = Field(default_factory=list, max_length=500)
    unavailable_location_ids: list[str] = Field(default_factory=list, max_length=500)
    capacity_overrides: dict[str, StrictInt] = Field(default_factory=dict, max_length=500)
    cost_multipliers: dict[str, float] = Field(default_factory=dict, max_length=500)
    transit_time_multipliers: dict[str, float] = Field(default_factory=dict, max_length=500)
    transit_time_additions: dict[str, float] = Field(default_factory=dict, max_length=500)

    @model_validator(mode="after")
    def validate_name_and_values(self) -> "GlobalScenarioCreateRequest":
        if not self.name.strip():
            raise ValueError("scenario name must be non-empty")
        for label, values, minimum in (
            ("cost multiplier", self.cost_multipliers, 1),
            ("transit-time multiplier", self.transit_time_multipliers, 1),
            ("transit-time addition", self.transit_time_additions, 0),
        ):
            if any(not isfinite(value) or value < minimum for value in values.values()):
                raise ValueError(f"{label} values must be finite and at least {minimum}")
        if any(isinstance(value, bool) or value < 0 for value in self.capacity_overrides.values()):
            raise ValueError("capacity overrides must be non-negative integers")
        return self


class GlobalDemoScenarioResponse(BaseModel):
    id: str
    name: str
    business_problem: str
    shipment_ids: list[str]
    scenario_id: str | None
    constraints: list[str]
    alternatives: list[str]
    synthetic: bool = True


class NetworkResponse(BaseModel):
    id: str
    name: str
    synthetic: bool = True
    quantity_unit: str
    cost_unit: str
    time_unit: str
    carbon_unit: str
    nodes: list[NetworkNode]
    links: list[NetworkLink]
    scenarios: list[NetworkScenario]


class GlobalShipment(BaseModel):
    id: str
    origin_id: str
    origin_name: str
    destination_id: str
    destination_name: str
    quantity: int
    quantity_unit: str
    cargo_category: str
    priority: int
    deadline: float
    deadline_unit: str
    delay_penalty_per_day: float
    maximum_transit_time: float
    departure_time: datetime
    synthetic: bool = True


class ObjectiveWeightsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cost: int = Field(default=40, ge=0, le=100)
    delivery_time: int = Field(default=25, ge=0, le=100)
    carbon: int = Field(default=20, ge=0, le=100)
    resilience: int = Field(default=15, ge=0, le=100)

    @model_validator(mode="after")
    def validate_total(self) -> "ObjectiveWeightsInput":
        if self.cost + self.delivery_time + self.carbon + self.resilience != 100:
            raise ValueError("objective weights must total 100")
        return self


class GlobalRoutesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shipment_id: str = Field(min_length=1)
    scenario_id: str | None = None
    max_routes: int = Field(default=8, ge=1, le=8)


class RouteIntelligenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shipment_id: str = Field(min_length=1)
    scenario_id: str | None = None
    weights: ObjectiveWeightsInput = Field(default_factory=ObjectiveWeightsInput)
    max_routes: int = Field(default=8, ge=1, le=8)
    shipment_ids: list[str] | None = Field(default=None, min_length=1, max_length=8)


class GlobalOptimizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str | None = "synthetic-suez-capacity-restriction"
    weights: ObjectiveWeightsInput = Field(default_factory=ObjectiveWeightsInput)
    max_routes: int = Field(default=8, ge=1, le=8)
    shipment_ids: list[str] | None = Field(default=None, min_length=1, max_length=8)


class RouteLegResponse(BaseModel):
    link_id: str
    origin_id: str
    destination_id: str
    mode: str
    distance_km: float
    transit_time: float
    freight_cost: float
    carbon_kg: float
    capacity: int | None
    geometry: list[tuple[float, float]]
    resilience_exposure: float | None = Field(
        default=None,
        description="Synthetic link exposure; null when a legacy link cannot be matched to current network data.",
    )


class CandidateRouteResponse(BaseModel):
    id: str
    shipment_id: str
    location_ids: list[str]
    link_ids: list[str]
    legs: list[RouteLegResponse]
    modes: list[str]
    distance_km: float
    transit_time: float
    freight_cost: float
    carbon_kg: float
    resilience_exposure: float
    transfer_count: int
    bottleneck_capacity: int | None
    geometry: list[tuple[float, float]]


class RouteDeltaResponse(BaseModel):
    baseline_route_id: str
    cost_savings: float
    cost_savings_percent: float | None
    time_savings_days: float
    carbon_savings_kg: float
    carbon_savings_percent: float | None


class RouteMetricContribution(BaseModel):
    link_id: str
    mode: str | None = None
    value: float
    unit: str


class RouteCapacityConstraint(BaseModel):
    link_id: str
    quantity: int
    capacity: int
    utilization: float


class RouteAnalysisResponse(BaseModel):
    route_id: str
    total_cost: float
    delay_penalty: float
    deadline_met: bool | None
    deadline_slack_days: float | None
    balanced_score: float
    maximum_capacity_utilization: float | None
    route_feasible: bool
    feasibility_constraints: list[str]
    capacity_constraints: list[RouteCapacityConstraint]
    transfer_count: int
    transfer_cost_modelled: bool = False
    handling_cost_modelled: bool = False
    cost_drivers: list[RouteMetricContribution]
    time_drivers: list[RouteMetricContribution]
    carbon_hotspots: list[RouteMetricContribution]
    disruption_exposure: float
    recovery_recommendation: str
    carbon_by_mode_kg: dict[str, float]
    largest_cost_leg_id: str | None
    largest_carbon_leg_id: str | None
    delta_vs_baseline: RouteDeltaResponse
    recommendation: str
    advantages: list[str]
    tradeoffs: list[str]
    analysis_type: str = "deterministic_rule_based"
    uses_llm: bool = False


class RouteIntelligenceResponse(BaseModel):
    shipment_id: str
    assignment_shipment_ids: list[str] = Field(default_factory=list)
    scenario_id: str | None
    synthetic: bool = True
    recommended_route_id: str
    assignment_route_id: str | None
    baseline_route: CandidateRouteResponse
    routes: list[CandidateRouteResponse]
    rankings: dict[str, list[str]]
    analyses: dict[str, RouteAnalysisResponse]
    recovery_feasible: bool
    normalization_references: dict[str, float]
    assumptions: list[str]


class DecisionQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shipment_id: str = Field(min_length=1)
    question: str = Field(min_length=1, max_length=500)
    route_id: str | None = None


class DecisionAnswerResponse(BaseModel):
    run_id: str
    shipment_id: str
    route_id: str
    answer: str
    analysis_type: str
    uses_llm: bool
    source_data: dict[str, Any]


class PlanMetricsResponse(BaseModel):
    freight_cost: float
    delay_penalty: float
    total_cost: float
    delivery_time: float
    carbon_kg: float
    resilience_exposure: float
    weighted_objective: float


class RouteAssignmentResponse(BaseModel):
    routes: dict[str, CandidateRouteResponse]
    alternatives: dict[str, list[CandidateRouteResponse]]
    metrics: PlanMetricsResponse
    capacity_usage: dict[str, int]
    capacity_utilization: dict[str, float]
    method: str


class ObjectiveReferencesResponse(BaseModel):
    cost: float
    delivery_time: float
    carbon: float
    resilience: float


class GlobalOptimizationResult(BaseModel):
    id: str
    status: str
    synthetic: bool = True
    scenario_id: str | None
    scenario_snapshot: NetworkScenario | None = None
    shipment_ids: list[str] = Field(default_factory=list)
    weights: ObjectiveWeightsInput
    normalization_references: ObjectiveReferencesResponse
    recovery_feasible: bool
    failure_reason: str | None
    baseline: RouteAssignmentResponse
    recovery: RouteAssignmentResponse | None
    algorithm: str
    optimality_scope: str


class GlobalOptimizationRecord(BaseModel):
    id: str
    status: str
    created_at: datetime
    scenario_id: str | None
    weights: ObjectiveWeightsInput
    result: GlobalOptimizationResult | None = None
    error: str | None = None


class GlobalOptimizationListResponse(BaseModel):
    items: list[GlobalOptimizationRecord]


class ShipmentPositionResponse(BaseModel):
    shipment_id: str
    status: str
    position: tuple[float, float]
    current_leg_id: str | None
    current_mode: str | None
    elapsed_time: float
    remaining_time: float
    departure_time: datetime
    estimated_arrival: datetime
    time_unit: str


class HealthResponse(BaseModel):
    status: str
    service: str


JsonObject = dict[str, Any]
