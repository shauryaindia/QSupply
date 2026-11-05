"""Pydantic request and response models for the optional QSupply API."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    description: str
    synthetic: bool = True
    closed_link_ids: list[str]
    unavailable_location_ids: list[str]
    capacity_overrides: dict[str, int]
    cost_multipliers: dict[str, float]
    transit_time_multipliers: dict[str, float]


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


class GlobalOptimizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str | None = "synthetic-suez-capacity-restriction"
    weights: ObjectiveWeightsInput = Field(default_factory=ObjectiveWeightsInput)
    max_routes: int = Field(default=8, ge=1, le=8)


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
    resilience_exposure: float


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


class RouteAnalysisResponse(BaseModel):
    route_id: str
    total_cost: float
    delay_penalty: float
    deadline_met: bool | None
    deadline_slack_days: float | None
    balanced_score: float
    maximum_capacity_utilization: float | None
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
