"""Deterministic synthetic instances exposed by the local dashboard API."""

from functools import lru_cache

from qsupply import generate_synthetic_cvrp
from qsupply.network import (
    DisruptionScenario,
    Location,
    LocationKind,
    TransportationNetwork,
    TransportLink,
    TransportMode,
)

from .schemas import InstanceSummary, NetworkLink, NetworkNode, NetworkResponse, NetworkScenario


CVRP_CUSTOMER_COUNTS = (5, 7, 9, 11)
CVRP_BASE_SEED = 2026


@lru_cache(maxsize=None)
def get_cvrp_instance(instance_id: str):
    try:
        customer_count = int(instance_id.removeprefix("synthetic-"))
    except ValueError as error:
        raise KeyError(instance_id) from error
    if instance_id != f"synthetic-{customer_count}" or customer_count not in CVRP_CUSTOMER_COUNTS:
        raise KeyError(instance_id)
    return generate_synthetic_cvrp(customer_count, CVRP_BASE_SEED + customer_count)


def list_cvrp_instances() -> list[InstanceSummary]:
    return [
        InstanceSummary(
            id=f"synthetic-{count}",
            name=f"Synthetic CVRP ({count} customers)",
            customer_count=count,
            seed=CVRP_BASE_SEED + count,
            exact_supported=count <= 10,
        )
        for count in CVRP_CUSTOMER_COUNTS
    ]


@lru_cache(maxsize=1)
def synthetic_network_response() -> NetworkResponse:
    locations = {
        location.id: location
        for location in (
            Location("mumbai-factory", LocationKind.FACTORY, "IN"),
            Location("chennai-factory", LocationKind.FACTORY, "IN"),
            Location("mumbai-port", LocationKind.PORT, "IN"),
            Location("chennai-port", LocationKind.PORT, "IN"),
            Location("delhi-rail", LocationKind.RAIL_TERMINAL, "IN"),
            Location("hormuz-hub", LocationKind.PORT),
            Location("suez-hub", LocationKind.PORT, "EG"),
            Location("cape-hub", LocationKind.PORT, "ZA"),
            Location("warsaw-rail", LocationKind.RAIL_TERMINAL, "PL"),
            Location("rotterdam-port", LocationKind.PORT, "NL"),
            Location("frankfurt-airport", LocationKind.AIRPORT, "DE"),
            Location("rotterdam-dc", LocationKind.DESTINATION, "NL"),
            Location("hamburg-dc", LocationKind.DESTINATION, "DE"),
        )
    }
    links = (
        TransportLink("road-mumbai-port", "mumbai-factory", "mumbai-port", TransportMode.ROAD, 40, "load_unit", 20, 8, 1, 0.6),
        TransportLink("road-chennai-port", "chennai-factory", "chennai-port", TransportMode.ROAD, 35, "load_unit", 18, 7, 1, 0.5),
        TransportLink("rail-chennai-delhi", "chennai-factory", "delhi-rail", TransportMode.RAIL, 24, "load_unit", 12, 5, 3, 0.3),
        TransportLink("rail-delhi-warsaw", "delhi-rail", "warsaw-rail", TransportMode.RAIL, 18, "load_unit", 90, 28, 12, 1.8),
        TransportLink("rail-warsaw-rotterdam", "warsaw-rail", "rotterdam-dc", TransportMode.RAIL, 16, "load_unit", 24, 9, 2, 0.5),
        TransportLink("sea-mumbai-hormuz", "mumbai-port", "hormuz-hub", TransportMode.SEA, 60, "load_unit", 35, 12, 4, 2.1),
        TransportLink("sea-chennai-hormuz", "chennai-port", "hormuz-hub", TransportMode.SEA, 55, "load_unit", 32, 11, 4, 2.0),
        TransportLink("sea-hormuz", "hormuz-hub", "suez-hub", TransportMode.SEA, 45, "load_unit", 40, 13, 5, 2.3),
        TransportLink("sea-suez-rotterdam", "suez-hub", "rotterdam-port", TransportMode.SEA, 42, "load_unit", 55, 15, 7, 2.7),
        TransportLink("sea-mumbai-cape", "mumbai-port", "cape-hub", TransportMode.SEA, 28, "load_unit", 70, 19, 12, 3.2),
        TransportLink("sea-chennai-cape", "chennai-port", "cape-hub", TransportMode.SEA, 26, "load_unit", 66, 18, 12, 3.1),
        TransportLink("sea-cape-rotterdam", "cape-hub", "rotterdam-port", TransportMode.SEA, 30, "load_unit", 72, 20, 13, 3.4),
        TransportLink("road-rotterdam-dc", "rotterdam-port", "rotterdam-dc", TransportMode.ROAD, 22, "load_unit", 8, 4, 1, 0.2),
        TransportLink("air-mumbai-frankfurt", "mumbai-factory", "frankfurt-airport", TransportMode.AIR, 12, "load_unit", 85, 40, 1, 8.0),
        TransportLink("air-chennai-frankfurt", "chennai-factory", "frankfurt-airport", TransportMode.AIR, 10, "load_unit", 90, 42, 1, 8.2),
        TransportLink("road-frankfurt-hamburg", "frankfurt-airport", "hamburg-dc", TransportMode.ROAD, 18, "load_unit", 16, 6, 1, 0.4),
        TransportLink("road-frankfurt-rotterdam", "frankfurt-airport", "rotterdam-dc", TransportMode.ROAD, 18, "load_unit", 18, 6, 1, 0.4),
    )
    network = TransportationNetwork(
        locations=locations,
        links=links,
        quantity_unit="load_unit",
        cost_unit="synthetic_cost_unit",
        time_unit="day",
        carbon_unit="kgCO2e",
    )
    scenario = DisruptionScenario(
        id="synthetic-hormuz-closure",
        closed_link_ids={"sea-hormuz"},
        capacity_overrides={"rail-delhi-warsaw": 8},
        cost_multipliers={"sea-cape-rotterdam": 1.15},
    )
    scenario.validate_for(network)
    link_items = [
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
        )
        for link in network.links
    ]
    return NetworkResponse(
        id="synthetic-india-europe",
        name="India–Europe multimodal network (synthetic)",
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
            )
            for location in network.locations.values()
        ],
        links=link_items,
        scenarios=[
            NetworkScenario(
                id=scenario.id,
                description="Synthetic corridor-closure scenario; no route recovery is computed.",
                closed_link_ids=sorted(scenario.closed_link_ids),
                unavailable_location_ids=sorted(scenario.unavailable_location_ids),
                capacity_overrides=dict(scenario.capacity_overrides),
                cost_multipliers={key: float(value) for key, value in scenario.cost_multipliers.items()},
                transit_time_multipliers={key: float(value) for key, value in scenario.transit_time_multipliers.items()},
            )
        ],
    )
