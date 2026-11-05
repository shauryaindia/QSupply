"""API serialization and orchestration for the synthetic global network slice."""

from datetime import datetime
from typing import Any

from qsupply.network.global_demo import (
    GlobalDemoScenario,
    global_demo_network,
    global_demo_disruptions,
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
from qsupply.network.insights import (
    DeterministicDecisionSupportProvider,
    analyze_route_alternatives,
)
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


def _scenario_inputs(scenario: DisruptionScenario) -> dict[str, Any]:
    return {
        "closed_link_ids": sorted(scenario.closed_link_ids),
        "unavailable_location_ids": sorted(scenario.unavailable_location_ids),
        "capacity_overrides": dict(scenario.capacity_overrides),
        "cost_multipliers": dict(scenario.cost_multipliers),
        "transit_time_multipliers": dict(scenario.transit_time_multipliers),
        "transit_time_additions": dict(scenario.transit_time_additions),
    }


def scenario_response(
    scenario: DisruptionScenario,
    *,
    name: str,
    description: str,
    custom: bool = False,
    created_at=None,
) -> NetworkScenario:
    inputs = _scenario_inputs(scenario)
    return NetworkScenario(
        id=scenario.id,
        name=name,
        description=description,
        synthetic=True,
        custom=custom,
        created_at=created_at,
        **inputs,
    )


def _stored_scenario(record: dict[str, Any]) -> DisruptionScenario:
    return DisruptionScenario(id=record["id"], **record["inputs"])


def global_network_response(scenario_store=None) -> NetworkResponse:
    network = global_demo_network()
    scenario_labels = {
        "synthetic-suez-capacity-restriction": (
            "Synthetic Suez capacity restriction",
            "Capacity and freight-cost overlay on a synthetic Suez-area route; not a live alert.",
        ),
        "synthetic-india-uae-combined-restriction": (
            "India–UAE combined port restriction",
            "Synthetic sea capacity reduction, rate increase, and additive port delay.",
        ),
        "synthetic-china-us-port-closure": (
            "China–US Los Angeles sea-link closure",
            "Closes one synthetic transpacific link to test alternate gateway recovery.",
        ),
        "synthetic-singapore-customs-delay": (
            "Singapore–Australia customs delay",
            "Adds a synthetic customs delay to one sea connection.",
        ),
        "synthetic-transatlantic-rate-surge": (
            "Transatlantic rate and time increase",
            "Applies synthetic ocean freight and transit-time multipliers.",
        ),
        "synthetic-india-rail-interruption": (
            "India domestic rail interruption",
            "Closes a synthetic rail link and lowers road capacity on an alternative corridor.",
        ),
        "synthetic-frankfurt-airport-disruption": (
            "Frankfurt air-link disruption",
            "Closes one synthetic air connection for route comparison.",
        ),
        "synthetic-eurasian-rail-restriction": (
            "Eurasian rail capacity restriction",
            "Reduces capacity and adds time on synthetic Eurasian rail links; border clearance is not modeled.",
        ),
        "synthetic-mumbai-road-capacity-reduction": (
            "Mumbai road capacity reduction",
            "Reduces synthetic road access capacity near Mumbai.",
        ),
    }
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
            *(
                scenario_response(
                    scenario,
                    name=scenario_labels[scenario.id][0],
                    description=scenario_labels[scenario.id][1],
                )
                for scenario in global_demo_disruptions()
            ),
            *(
                scenario_response(
                    _stored_scenario(record),
                    name=record["name"],
                    description=record["description"],
                    custom=True,
                    created_at=record["created_at"],
                )
                for record in (scenario_store.list_global_scenarios() if scenario_store else [])
            ),
        ],
    )


def global_demo_response(demo: GlobalDemoScenario) -> dict[str, Any]:
    return {
        "id": demo.id,
        "name": demo.name,
        "business_problem": demo.business_problem,
        "shipment_ids": list(demo.shipment_ids),
        "scenario_id": demo.scenario_id,
        "constraints": list(demo.constraints),
        "alternatives": list(demo.alternatives),
        "synthetic": True,
    }


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


def get_global_scenario(scenario_id: str | None, scenario_store=None) -> DisruptionScenario | None:
    if scenario_id is None:
        return None
    for scenario in global_demo_disruptions():
        if scenario.id == scenario_id:
            return scenario
    record = scenario_store.get_global_scenario(scenario_id) if scenario_store else None
    return _stored_scenario(record) if record else None


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
    shipment_id: str, scenario_id: str | None, max_routes: int, scenario_store=None
) -> list[CandidateRouteResponse]:
    profile = get_shipment_profile(shipment_id)
    if profile is None:
        raise KeyError(shipment_id)
    scenario = get_global_scenario(scenario_id, scenario_store)
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
    scenario_store=None,
    shipment_ids: list[str] | None = None,
) -> dict[str, Any]:
    scenario = get_global_scenario(scenario_id, scenario_store)
    if scenario_id is not None and scenario is None:
        raise KeyError(scenario_id)
    profile_by_id = {profile.request.id: profile for profile in global_demo_shipments()}
    if shipment_ids is None:
        # Keep the legacy API default stable; new demo workflows select explicit shipments.
        profiles = tuple(profile_by_id[item] for item in ("EXP-104", "EXP-205"))
    else:
        if not shipment_ids or len(shipment_ids) > 8 or len(set(shipment_ids)) != len(shipment_ids):
            raise ValueError("shipment_ids must contain between 1 and 8 unique shipment IDs")
        try:
            profiles = tuple(profile_by_id[item] for item in shipment_ids)
        except KeyError as error:
            raise KeyError(error.args[0]) from error
    comparison = compare_recovery(
        global_demo_network(),
        profiles,
        scenario,
        ObjectiveWeights(**weights),
        max_routes=max_routes,
    )
    stored_scenario = (
        scenario_store.get_global_scenario(scenario.id)
        if scenario is not None
        and scenario.id != global_demo_scenario().id
        and scenario_store is not None
        else None
    )
    built_in_scenario = (
        next(
            item
            for item in global_network_response().scenarios
            if item.id == scenario.id
        )
        if scenario is not None and stored_scenario is None
        else None
    )
    scenario_snapshot = (
        scenario_response(
            scenario,
            name=(built_in_scenario.name if stored_scenario is None else stored_scenario["name"]),
            description=(built_in_scenario.description if stored_scenario is None else stored_scenario["description"]),
            custom=stored_scenario is not None,
            created_at=(stored_scenario["created_at"] if stored_scenario else None),
        ).model_dump(mode="json")
        if scenario is not None
        else None
    )
    return {
        "id": run_id,
        "status": "completed",
        "synthetic": True,
        "scenario_id": comparison.scenario_id,
        "scenario_snapshot": scenario_snapshot,
        "shipment_ids": [profile.request.id for profile in profiles],
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
    scenario_store=None,
    shipment_ids: list[str] | None = None,
) -> RouteIntelligenceResponse:
    profile = get_shipment_profile(shipment_id)
    if profile is None:
        raise KeyError(shipment_id)
    scenario = get_global_scenario(scenario_id, scenario_store)
    if scenario_id is not None and scenario is None:
        raise KeyError(scenario_id)
    profile_by_id = {item.request.id: item for item in global_demo_shipments()}
    selected_ids = shipment_ids or [shipment_id]
    if not selected_ids or len(selected_ids) > 8 or len(set(selected_ids)) != len(selected_ids):
        raise ValueError("shipment_ids must contain between 1 and 8 unique shipment IDs")
    if shipment_id not in selected_ids:
        raise ValueError("shipment_id must be included in shipment_ids")
    try:
        selected_profiles = tuple(profile_by_id[item] for item in selected_ids)
    except KeyError as error:
        raise KeyError(error.args[0]) from error
    comparison = compare_recovery(
        global_demo_network(),
        selected_profiles,
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
    assignment_route_id = (
        assignment.routes[shipment_id].id if assignment is not None else None
    )
    for route_id, analysis in analyses.items():
        if scenario_id is None:
            analysis["recovery_recommendation"] = (
                "This route is part of the baseline joint assignment."
                if assignment_route_id == route_id
                else f"The baseline joint assignment selected {assignment_route_id}."
            )
        elif assignment_route_id is None:
            analysis["recovery_recommendation"] = (
                "No shared-capacity-feasible joint recovery was found over the generated candidates."
            )
        else:
            analysis["recovery_recommendation"] = (
                "Selected by the joint recovery assignment."
                if assignment_route_id == route_id
                else f"The joint recovery assignment selected {assignment_route_id}."
            )
    return RouteIntelligenceResponse(
        shipment_id=shipment_id,
        assignment_shipment_ids=list(selected_ids),
        scenario_id=scenario_id,
        recommended_route_id=recommended_id,
        assignment_route_id=assignment_route_id,
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


def answer_decision_question(
    record: dict[str, Any], shipment_id: str, question: str, route_id: str | None = None
) -> dict[str, Any]:
    result = record.get("result")
    if not result:
        raise ValueError("completed optimization result is not available")
    profile = get_shipment_profile(shipment_id)
    if profile is None:
        raise KeyError(shipment_id)
    routes: dict[str, dict[str, Any]] = {}
    for plan_name in ("baseline", "recovery"):
        plan = result.get(plan_name)
        if not plan:
            continue
        selected = plan.get("routes", {}).get(shipment_id)
        if selected:
            routes[selected["id"]] = selected
        for alternative in plan.get("alternatives", {}).get(shipment_id, []):
            routes[alternative["id"]] = alternative
    if route_id is None:
        route = (result.get("recovery") or {}).get("routes", {}).get(shipment_id)
        route = route or result.get("baseline", {}).get("routes", {}).get(shipment_id)
    else:
        route = routes.get(route_id)
    if route is None:
        raise KeyError(route_id or shipment_id)

    deadline = profile.request.deadline
    delay_days = (
        max(0.0, float(route["transit_time"]) - float(deadline))
        if deadline is not None
        else 0.0
    )
    delay_penalty = delay_days * float(profile.delay_penalty_per_day)
    baseline_route = result.get("baseline", {}).get("routes", {}).get(shipment_id)
    baseline_cost = None
    if baseline_route:
        baseline_delay = (
            max(0.0, float(baseline_route["transit_time"]) - float(deadline))
            if deadline is not None
            else 0.0
        )
        baseline_cost = float(baseline_route["freight_cost"]) + baseline_delay * float(profile.delay_penalty_per_day)
    carbon_by_mode: dict[str, float] = {}
    capacities = []
    for leg in route["legs"]:
        carbon_by_mode[leg["mode"]] = carbon_by_mode.get(leg["mode"], 0.0) + float(leg["carbon_kg"])
        if leg.get("capacity") is not None:
            capacities.append({
                "link_id": leg["link_id"],
                "quantity": profile.request.quantity,
                "capacity": leg["capacity"],
                "utilization": profile.request.quantity / leg["capacity"] if leg["capacity"] else None,
            })
    slack = None if deadline is None else float(deadline) - float(route["transit_time"])
    source_data = {
        "scenario_snapshot": result.get("scenario_snapshot"),
        "route_id": route["id"],
        "freight_cost": float(route["freight_cost"]),
        "delay_penalty": delay_penalty,
        "total_cost": float(route["freight_cost"]) + delay_penalty,
        "cost_savings_vs_baseline": (
            baseline_cost - float(route["freight_cost"]) - delay_penalty
            if baseline_cost is not None
            else None
        ),
        "transit_time_days": float(route["transit_time"]),
        "deadline_slack_days": slack,
        "time_savings_vs_baseline_days": (
            float(baseline_route["transit_time"]) - float(route["transit_time"])
            if baseline_route
            else None
        ),
        "carbon_estimate_kgco2e": float(route["carbon_kg"]),
        "carbon_by_mode_kgco2e": carbon_by_mode,
        "carbon_savings_vs_baseline_kgco2e": (
            float(baseline_route["carbon_kg"]) - float(route["carbon_kg"])
            if baseline_route
            else None
        ),
        "distance_km": float(route["distance_km"]),
        "transfer_count": int(route["transfer_count"]),
        "resilience_exposure": float(route["resilience_exposure"]),
        "capacity_constraints": capacities,
        "legs": route["legs"],
        "recovery_feasible": result["recovery_feasible"],
    }
    provider = DeterministicDecisionSupportProvider()
    return {
        "run_id": record["id"],
        "shipment_id": shipment_id,
        "route_id": route["id"],
        "answer": provider.answer(question, source_data),
        "analysis_type": provider.name,
        "uses_llm": provider.uses_llm,
        "source_data": source_data,
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
