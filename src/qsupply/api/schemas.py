"""Pydantic request and response models for the optional QSupply API."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class HealthResponse(BaseModel):
    status: str
    service: str


JsonObject = dict[str, Any]
