"""API serialization and orchestration for the synthetic global network slice."""

from datetime import datetime
from typing import Any

from qsupply.network.global_demo import (
    global_demo_network,
    global_demo_scenario,
    global_demo_shipments,
)
from qsupply.network.models import DisruptionScenario, TransportMode
from qsupply.network.planning import (
    ObjectiveReferences,
    CandidateRoute,
    ObjectiveWeights,
    compare_recovery,
    simulate_movement,
)
from qsupply.network.insights import analyze_route_alternatives
from qsupply.network.routing import (
    RouteLeg,
    generate_candidate_routes,
    validate_candidate_route,
)

from .schemas import (
    CandidateRouteResponse,
    GlobalShipment,
    NetworkLink,
    NetworkNode,
    NetworkResponse,
    NetworkScenario,
    RouteLegResponse,
    RouteAnalysisResponse,
    RouteIntelligenceResponse,
)


def global_network_response() -> NetworkResponse:
    network = global_demo_network()
    scenario = global_demo_scenario()
    return NetworkResponse(
        id="synthetic-global-network-v1",
        name="Global multimodal demonstration network",
        synthetic=True,
        quantity_unit=network.quantity_unit,
        cost_unit=network.cost_unit,
        time_unit=network.time_unit,
        carbon_unit=network.carbon_unit,
        nodes=[
            NetworkNode(
                id=location.id,
                label=location.id.replace("-", " ").title(),
                kind=location.kind.value,
                country_code=location.country_code,
                country_name=location.country_name,
                region=location.region,
                timezone=location.timezone,
                latitude=float(location.latitude),
                longitude=float(location.longitude),
                transfer_modes=sorted(mode.value for mode in location.transfer_modes),
            )
            for location in network.locations.values()
        ],
        links=[
            NetworkLink(
                id=link.id,
                source=link.origin_id,
                target=link.destination_id,
                mode=link.mode.value,
                capacity=link.capacity,
                capacity_unit=link.capacity_unit,
                fixed_cost=float(link.fixed_cost),
                variable_cost_per_quantity_unit=float(link.variable_cost_per_quantity_unit),
                transit_time=float(link.transit_time),
                carbon_per_quantity_unit=float(link.carbon_per_quantity_unit),
                available=link.available,
                capabilities=sorted(link.capabilities),
                distance_km=float(link.distance_km),
                geometry=[(float(lat), float(lon)) for lat, lon in link.geometry],
                resilience_exposure=float(link.resilience_exposure),
            )
            for link in network.links
        ],
        scenarios=[
            NetworkScenario(
                id=scenario.id,
                description=(
                    "Synthetic Suez corridor capacity restriction. This is a scenario "
                    "input, not a live disruption alert."
                ),
                closed_link_ids=sorted(scenario.closed_link_ids),
                unavailable_location_ids=sorted(scenario.unavailable_location_ids),
                capacity_overrides=dict(scenario.capacity_overrides),
                cost_multipliers={key: float(value) for key, value in scenario.cost_multipliers.items()},
                transit_time_multipliers={key: float(value) for key, value in scenario.transit_time_multipliers.items()},
            )
        ],
    )


def shipment_response(profile) -> GlobalShipment:
    network = global_demo_network()
    request = profile.request
    return GlobalShipment(
        id=request.id,
        origin_id=request.origin_id,
        origin_name=network.locations[request.origin_id].id.replace("-", " ").title(),
        destination_id=request.destination_id,
        destination_name=network.locations[request.destination_id].id.replace("-", " ").title(),
        quantity=request.quantity,
        quantity_unit=request.quantity_unit,
        cargo_category=profile.cargo_category,
        priority=profile.priority,
        deadline=float(request.deadline),
        deadline_unit=request.deadline_unit,
        delay_penalty_per_day=float(profile.delay_penalty_per_day),
        maximum_transit_time=float(profile.maximum_transit_time),
        departure_time=profile.departure_time,
        synthetic=True,
    )


def get_shipment_profile(shipment_id: str):
    for profile in global_demo_shipments():
        if profile.request.id == shipment_id:
            return profile
    return None


def get_global_scenario(scenario_id: str | None) -> DisruptionScenario | None:
    if scenario_id is None:
        return None
    scenario = global_demo_scenario()
    if scenario.id != scenario_id:
        return None
    return scenario


def route_response(route: CandidateRoute) -> CandidateRouteResponse:
    return CandidateRouteResponse(
        id=route.id,
        shipment_id=route.shipment_id,
        location_ids=list(route.location_ids),
        link_ids=[leg.link_id for leg in route.legs],
        legs=[
            RouteLegResponse(
                link_id=leg.link_id,
                origin_id=leg.origin_id,
                destination_id=leg.destination_id,
                mode=leg.mode.value,
                distance_km=leg.distance_km,
                transit_time=leg.transit_time,
                freight_cost=leg.freight_cost,
                carbon_kg=leg.carbon_kg,
                capacity=leg.capacity,
                geometry=list(leg.geometry),
                resilience_exposure=leg.resilience_exposure,
            )
            for leg in route.legs
        ],
        modes=[mode.value for mode in route.modes],
        distance_km=route.distance_km,
        transit_time=route.transit_time,
        freight_cost=route.freight_cost,
        carbon_kg=route.carbon_kg,
        resilience_exposure=route.resilience_exposure,
        transfer_count=route.transfer_count,
        bottleneck_capacity=route.bottleneck_capacity,
        geometry=list(route.geometry),
    )


def generate_shipment_routes(
    shipment_id: str, scenario_id: str | None, max_routes: int
) -> list[CandidateRouteResponse]:
    profile = get_shipment_profile(shipment_id)
    if profile is None:
        raise KeyError(shipment_id)
    scenario = get_global_scenario(scenario_id)
    if scenario_id is not None and scenario is None:
        raise KeyError(scenario_id)
    network = global_demo_network()
    routes = generate_candidate_routes(
        network, profile.request, scenario, max_routes=max_routes
    )
    routes = tuple(
        route
        for route in routes
        if route.transit_time <= profile.maximum_transit_time
    )
    for route in routes:
        validate_candidate_route(network, profile.request, route, scenario)
    return [route_response(route) for route in routes]


def _route_assignment_response(assignment, candidates) -> dict[str, Any]:
    selected = assignment.routes
    return {
        "routes": {key: route_response(route).model_dump(mode="json") for key, route in selected.items()},
        "alternatives": {
            key: [
                route_response(route).model_dump(mode="json")
                for route in candidates[key]
                if route.id != selected[key].id
            ]
            for key in selected
        },
        "metrics": {
            "freight_cost": assignment.metrics.freight_cost,
            "delay_penalty": assignment.metrics.delay_penalty,
            "total_cost": assignment.metrics.total_cost,
            "delivery_time": assignment.metrics.delivery_time,
            "carbon_kg": assignment.metrics.carbon_kg,
            "resilience_exposure": assignment.metrics.resilience_exposure,
            "weighted_objective": assignment.metrics.weighted_objective,
        },
        "capacity_usage": dict(assignment.capacity_usage),
        "capacity_utilization": dict(assignment.capacity_utilization),
        "method": assignment.method,
    }


def run_global_optimization(
    run_id: str,
    scenario_id: str | None,
    weights: dict[str, int],
    max_routes: int,
) -> dict[str, Any]:
    scenario = get_global_scenario(scenario_id)
    if scenario_id is not None and scenario is None:
        raise KeyError(scenario_id)
    profiles = global_demo_shipments()
    comparison = compare_recovery(
        global_demo_network(),
        profiles,
        scenario,
        ObjectiveWeights(**weights),
        max_routes=max_routes,
    )
    return {
        "id": run_id,
        "status": "completed",
        "synthetic": True,
        "scenario_id": comparison.scenario_id,
        "weights": weights,
        "normalization_references": {
            "cost": comparison.normalization_references.cost,
            "delivery_time": comparison.normalization_references.delivery_time,
            "carbon": comparison.normalization_references.carbon,
            "resilience": comparison.normalization_references.resilience,
        },
        "recovery_feasible": comparison.recovery_feasible,
        "failure_reason": comparison.failure_reason,
        "baseline": _route_assignment_response(
            comparison.baseline, comparison.baseline_candidates
        ),
        "recovery": (
            _route_assignment_response(comparison.recovery, comparison.recovery_candidates)
            if comparison.recovery is not None
            else None
        ),
        "algorithm": "bounded route generation + exact candidate assignment enumeration",
        "optimality_scope": "exact only over the generated candidate routes; route generation is bounded",
    }


def route_intelligence(
    shipment_id: str,
    scenario_id: str | None,
    weights: dict[str, int],
    max_routes: int,
) -> RouteIntelligenceResponse:
    profile = get_shipment_profile(shipment_id)
    if profile is None:
        raise KeyError(shipment_id)
    scenario = get_global_scenario(scenario_id)
    if scenario_id is not None and scenario is None:
        raise KeyError(scenario_id)
    comparison = compare_recovery(
        global_demo_network(),
        global_demo_shipments(),
        scenario,
        ObjectiveWeights(**weights),
        max_routes=max_routes,
    )
    options = (
        comparison.recovery_candidates[shipment_id]
        if scenario_id is not None
        else comparison.baseline_candidates[shipment_id]
    )
    if not options:
        raise ValueError("no feasible candidate routes exist under the selected scenario")
    baseline_route = comparison.baseline.routes[shipment_id]
    references = comparison.normalization_references
    assignment = comparison.recovery if scenario_id is not None else comparison.baseline
    recommended_id, rankings, analyses = analyze_route_alternatives(
        profile,
        options,
        baseline_route,
        ObjectiveWeights(**weights),
        references,
        scenario_id=scenario_id,
    )
    return RouteIntelligenceResponse(
        shipment_id=shipment_id,
        scenario_id=scenario_id,
        recommended_route_id=recommended_id,
        assignment_route_id=(
            assignment.routes[shipment_id].id if assignment is not None else None
        ),
        baseline_route=route_response(baseline_route),
        routes=[route_response(route) for route in options],
        rankings=rankings,
        analyses={
            route_id: RouteAnalysisResponse.model_validate(analysis)
            for route_id, analysis in analyses.items()
        },
        recovery_feasible=comparison.recovery_feasible,
        normalization_references={
            "cost": references.cost,
            "delivery_time": references.delivery_time,
            "carbon": references.carbon,
            "resilience": references.resilience,
        },
        assumptions=[
            "All route inputs and emissions factors in this demonstration are synthetic.",
            "Route cost includes synthetic fixed and per-load-unit link costs plus modeled deadline penalties.",
            "Customs delay, port handling, inventory holding cost, shipment weight, reliability and regulatory impact are not modeled.",
            "The recommendation is deterministic rule-based analysis; no LLM is used.",
        ],
    )


def movement_for_result(
    result: dict[str, Any], shipment_id: str, elapsed_time: float
) -> dict[str, Any]:
    profile = get_shipment_profile(shipment_id)
    if profile is None:
        raise KeyError(shipment_id)
    plan = result.get("recovery") or result.get("baseline")
    if plan is None or shipment_id not in plan["routes"]:
        raise ValueError("optimization result has no selected route for this shipment")
    route_data = plan["routes"][shipment_id]
    route = _route_from_dict(route_data)
    movement = simulate_movement(
        route,
        profile.departure_time,
        elapsed_time,
        global_demo_network().time_unit,
    )
    return {
        "shipment_id": shipment_id,
        **movement,
        "time_unit": global_demo_network().time_unit,
    }


def _route_from_dict(data: dict[str, Any]) -> CandidateRoute:
    legs = tuple(
        RouteLeg(
            link_id=leg["link_id"],
            origin_id=leg["origin_id"],
            destination_id=leg["destination_id"],
            mode=TransportMode(leg["mode"]),
            distance_km=leg["distance_km"],
            transit_time=leg["transit_time"],
            freight_cost=leg["freight_cost"],
            carbon_kg=leg["carbon_kg"],
            capacity=leg["capacity"],
            geometry=tuple(tuple(point) for point in leg["geometry"]),
            resilience_exposure=leg.get("resilience_exposure", 0.0),
        )
        for leg in data["legs"]
    )
    return CandidateRoute(
        id=data["id"],
        shipment_id=data["shipment_id"],
        location_ids=tuple(data["location_ids"]),
        legs=legs,
        modes=tuple(TransportMode(mode) for mode in data["modes"]),
        distance_km=data["distance_km"],
        transit_time=data["transit_time"],
        freight_cost=data["freight_cost"],
        carbon_kg=data["carbon_kg"],
        resilience_exposure=data["resilience_exposure"],
        transfer_count=data["transfer_count"],
        bottleneck_capacity=data["bottleneck_capacity"],
        geometry=tuple(tuple(point) for point in data["geometry"]),
    )


def timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
