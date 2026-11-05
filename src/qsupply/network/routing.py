"""Bounded deterministic multimodal route generation and independent validation."""

from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from math import isclose
from typing import Sequence

from .models import (
    DisruptionScenario,
    Location,
    ShipmentRequest,
    TransportationNetwork,
    TransportLink,
    TransportMode,
)

Coordinate = tuple[float, float]


@dataclass(frozen=True)
class RouteLeg:
    """One directed movement on a candidate route, with shipment-adjusted metrics."""

    link_id: str
    origin_id: str
    destination_id: str
    mode: TransportMode
    distance_km: float
    transit_time: float
    freight_cost: float
    carbon_kg: float
    capacity: int | None
    geometry: tuple[Coordinate, ...]


@dataclass(frozen=True)
class CandidateRoute:
    """A feasible path for one shipment under the supplied network overlay."""

    id: str
    shipment_id: str
    location_ids: tuple[str, ...]
    legs: tuple[RouteLeg, ...]
    modes: tuple[TransportMode, ...]
    distance_km: float
    transit_time: float
    freight_cost: float
    carbon_kg: float
    resilience_exposure: float
    transfer_count: int
    bottleneck_capacity: int | None
    geometry: tuple[Coordinate, ...]


@dataclass(frozen=True)
class _EffectiveLink:
    link: TransportLink
    capacity: int | None
    cost_multiplier: float
    time_multiplier: float
    rank_cost: float
    rank_time: float
    rank_carbon: float


def _effective_links(
    network: TransportationNetwork,
    shipment: ShipmentRequest,
    scenario: DisruptionScenario | None,
) -> dict[str, _EffectiveLink]:
    if scenario is not None:
        scenario.validate_for(network)
    missing_coordinates = [
        location.id
        for location in network.locations.values()
        if location.latitude is None or location.longitude is None
    ]
    if missing_coordinates:
        raise ValueError(
            f"geospatial route generation requires coordinates for every location; missing {missing_coordinates[:5]!r}"
        )
    missing_geometry = [
        link.id
        for link in network.links
        if link.distance_km is None or not link.geometry
    ]
    if missing_geometry:
        raise ValueError(
            f"geospatial route generation requires distance_km and geometry for every link; missing {missing_geometry[:5]!r}"
        )
    effective: dict[str, _EffectiveLink] = {}
    for link in network.links:
        if not link.available:
            continue
        if scenario is not None:
            if link.id in scenario.closed_link_ids:
                continue
            if link.origin_id in scenario.unavailable_location_ids:
                continue
            if link.destination_id in scenario.unavailable_location_ids:
                continue
        capacity = link.capacity
        if scenario is not None and link.id in scenario.capacity_overrides:
            capacity = scenario.capacity_overrides[link.id]
        if capacity is not None and capacity < shipment.quantity:
            continue
        if not shipment.required_capabilities.issubset(link.capabilities):
            continue
        cost_multiplier = (
            scenario.cost_multipliers.get(link.id, 1) if scenario is not None else 1
        )
        time_multiplier = (
            scenario.transit_time_multipliers.get(link.id, 1)
            if scenario is not None
            else 1
        )
        effective[link.id] = _EffectiveLink(
            link=link,
            capacity=capacity,
            cost_multiplier=float(cost_multiplier),
            time_multiplier=float(time_multiplier),
            rank_cost=float(link.fixed_cost + link.variable_cost_per_quantity_unit * shipment.quantity)
            * float(cost_multiplier),
            rank_time=float(link.transit_time) * float(time_multiplier),
            rank_carbon=float(link.carbon_per_quantity_unit) * shipment.quantity,
        )
    return effective


def _route_from_links(
    shipment: ShipmentRequest,
    links: Sequence[_EffectiveLink],
) -> CandidateRoute:
    if not links:
        raise ValueError("a route must contain at least one transport link")
    if links[0].link.origin_id != shipment.origin_id:
        raise ValueError("route does not start at the shipment origin")
    if links[-1].link.destination_id != shipment.destination_id:
        raise ValueError("route does not end at the shipment destination")

    location_ids = [links[0].link.origin_id]
    geometry: list[Coordinate] = []
    legs: list[RouteLeg] = []
    transfers = 0
    previous_mode: TransportMode | None = None
    for index, effective in enumerate(links):
        link = effective.link
        if location_ids[-1] != link.origin_id:
            raise ValueError("route links are not connected in order")
        if link.destination_id in location_ids:
            raise ValueError("candidate route must not repeat a location")
        if previous_mode is not None and previous_mode != link.mode:
            transfers += 1
        previous_mode = link.mode
        location_ids.append(link.destination_id)
        points = tuple((float(lat), float(lon)) for lat, lon in link.geometry)
        if not geometry:
            geometry.extend(points)
        else:
            geometry.extend(points[1:])
        legs.append(
            RouteLeg(
                link_id=link.id,
                origin_id=link.origin_id,
                destination_id=link.destination_id,
                mode=link.mode,
                distance_km=float(link.distance_km),
                transit_time=float(link.transit_time) * effective.time_multiplier,
                freight_cost=float(
                    (link.fixed_cost + link.variable_cost_per_quantity_unit * shipment.quantity)
                    * effective.cost_multiplier
                ),
                carbon_kg=float(link.carbon_per_quantity_unit * shipment.quantity),
                capacity=effective.capacity,
                geometry=points,
            )
        )
    return CandidateRoute(
        id=f"{shipment.id}:" + ":".join(link.link.id for link in links),
        shipment_id=shipment.id,
        location_ids=tuple(location_ids),
        legs=tuple(legs),
        modes=tuple(leg.mode for leg in legs),
        distance_km=sum(leg.distance_km for leg in legs),
        transit_time=sum(leg.transit_time for leg in legs),
        freight_cost=sum(leg.freight_cost for leg in legs),
        carbon_kg=sum(leg.carbon_kg for leg in legs),
        resilience_exposure=sum(effective.link.resilience_exposure for effective in links),
        transfer_count=transfers,
        bottleneck_capacity=(
            min(finite_capacities)
            if (finite_capacities := [item.capacity for item in links if item.capacity is not None])
            else None
        ),
        geometry=tuple(geometry),
    )


def generate_candidate_routes(
    network: TransportationNetwork,
    shipment: ShipmentRequest,
    scenario: DisruptionScenario | None = None,
    *,
    max_routes: int = 5,
    max_transfers: int = 4,
    max_expansions: int = 20_000,
) -> tuple[CandidateRoute, ...]:
    """Generate up to ``max_routes`` deterministic, simple feasible paths.

    A bounded best-first search ranks each link by normalized freight, time,
    carbon and exposure components. It never repeats a location, excludes
    unavailable/under-capacity links, and only changes transport mode at a
    location that explicitly supports both modes. It returns the best paths
    found by that ranking, not a proof that all paths in a large graph were
    enumerated.
    """
    if not isinstance(network, TransportationNetwork):
        raise TypeError("network must be a TransportationNetwork")
    network.validate_shipment(shipment)
    for value, name in ((max_routes, "max_routes"), (max_expansions, "max_expansions")):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
        if value <= 0:
            raise ValueError(f"{name} must be positive")
    if isinstance(max_transfers, bool) or not isinstance(max_transfers, int):
        raise TypeError("max_transfers must be an integer")
    if max_transfers < 0:
        raise ValueError("max_transfers must be non-negative")

    effective = _effective_links(network, shipment, scenario)
    adjacency: dict[str, list[_EffectiveLink]] = {}
    for item in effective.values():
        adjacency.setdefault(item.link.origin_id, []).append(item)
    for outgoing in adjacency.values():
        outgoing.sort(key=lambda item: item.link.id)

    if not adjacency.get(shipment.origin_id):
        return ()
    max_cost = max((item.rank_cost for item in effective.values()), default=1) or 1
    max_time = max((item.rank_time for item in effective.values()), default=1) or 1
    max_carbon = max((item.rank_carbon for item in effective.values()), default=1) or 1

    # Heap tuple fields provide stable lexicographic tie-breaking across runs.
    frontier: list[tuple[float, tuple[str, ...], str, tuple[str, ...], int, TransportMode | None]] = [
        (0.0, (), shipment.origin_id, (shipment.origin_id,), 0, None)
    ]
    routes: list[CandidateRoute] = []
    expansions = 0
    while frontier and len(routes) < max_routes and expansions < max_expansions:
        rank, link_ids, node_id, path, transfers, previous_mode = heappop(frontier)
        if node_id == shipment.destination_id and link_ids:
            route_links = [effective[link_id] for link_id in link_ids]
            routes.append(_route_from_links(shipment, route_links))
            continue
        expansions += 1
        visited = set(path)
        for item in adjacency.get(node_id, ()):
            link = item.link
            if link.destination_id in visited:
                continue
            next_transfers = transfers
            if previous_mode is not None and previous_mode != link.mode:
                location = network.locations[node_id]
                if previous_mode not in location.transfer_modes or link.mode not in location.transfer_modes:
                    continue
                next_transfers += 1
            if next_transfers > max_transfers:
                continue
            edge_rank = (
                item.rank_cost / max_cost
                + item.rank_time / max_time
                + item.rank_carbon / max_carbon
                + item.link.resilience_exposure
            )
            next_link_ids = (*link_ids, link.id)
            heappush(
                frontier,
                (
                    rank + edge_rank,
                    next_link_ids,
                    link.destination_id,
                    (*path, link.destination_id),
                    next_transfers,
                    link.mode,
                ),
            )
    return tuple(routes)


def validate_candidate_route(
    network: TransportationNetwork,
    shipment: ShipmentRequest,
    route: CandidateRoute,
    scenario: DisruptionScenario | None = None,
    *,
    max_transfers: int = 4,
) -> None:
    """Independently check route connectivity, capacity, overlays and metrics."""
    network.validate_shipment(shipment)
    if route.shipment_id != shipment.id:
        raise ValueError("route shipment ID does not match shipment")
    link_map = network.links_by_id
    effective = _effective_links(network, shipment, scenario)
    if len(route.legs) != len(route.location_ids) - 1 or not route.legs:
        raise ValueError("route locations and legs do not form a connected path")
    if route.location_ids[0] != shipment.origin_id or route.location_ids[-1] != shipment.destination_id:
        raise ValueError("route endpoints do not match shipment endpoints")
    if len(set(route.location_ids)) != len(route.location_ids):
        raise ValueError("route repeats a location")
    recalculated: list[_EffectiveLink] = []
    previous_mode: TransportMode | None = None
    for index, leg in enumerate(route.legs):
        link = link_map.get(leg.link_id)
        if link is None or link.origin_id != route.location_ids[index] or link.destination_id != route.location_ids[index + 1]:
            raise ValueError("route contains an unknown or disconnected link")
        if leg.link_id not in effective:
            raise ValueError(f"route uses unavailable or under-capacity link {leg.link_id!r}")
        if previous_mode is not None and previous_mode != link.mode:
            transfer_location = network.locations[link.origin_id]
            if (
                previous_mode not in transfer_location.transfer_modes
                or link.mode not in transfer_location.transfer_modes
            ):
                raise ValueError(
                    f"location {link.origin_id!r} does not support the route's mode transfer"
                )
        previous_mode = link.mode
        recalculated.append(effective[leg.link_id])
    expected = _route_from_links(shipment, recalculated)
    if expected.transfer_count > max_transfers:
        raise ValueError("route exceeds the maximum transfer count")
    for field in (
        "distance_km",
        "transit_time",
        "freight_cost",
        "carbon_kg",
        "resilience_exposure",
    ):
        if not isclose(getattr(route, field), getattr(expected, field), rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError(f"route {field} does not match independent recalculation")
    if route.geometry != expected.geometry:
        raise ValueError("route geometry does not match its transport links")
