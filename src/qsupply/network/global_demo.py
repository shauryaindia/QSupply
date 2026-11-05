"""Deterministic synthetic global network and shipment scenario for demos."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from types import MappingProxyType

from .models import (
    DisruptionScenario,
    Location,
    LocationKind,
    ShipmentRequest,
    TransportationNetwork,
    TransportLink,
    TransportMode,
)
from .planning import ShipmentProfile


@lru_cache(maxsize=1)
def global_demo_network() -> TransportationNetwork:
    """Return an illustrative global graph; costs and corridors are synthetic."""
    all_modes = frozenset(TransportMode)
    modes = {
        "shanghai-hub": all_modes,
        "shanghai-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "shanghai-airport": frozenset({TransportMode.AIR, TransportMode.ROAD}),
        "shanghai-rail": frozenset({TransportMode.RAIL, TransportMode.ROAD}),
        "shenzhen": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "singapore-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "colombo-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "mumbai-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "mumbai-airport": frozenset({TransportMode.AIR, TransportMode.ROAD}),
        "delhi-rail": frozenset({TransportMode.RAIL, TransportMode.ROAD}),
        "dubai": frozenset({TransportMode.ROAD}),
        "jebel-ali": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "durban-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "rotterdam-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "rotterdam-hub": frozenset({TransportMode.ROAD, TransportMode.RAIL}),
        "frankfurt-airport": frozenset({TransportMode.AIR, TransportMode.ROAD, TransportMode.RAIL}),
        "frankfurt-rail": frozenset({TransportMode.RAIL, TransportMode.ROAD}),
        "hamburg-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "hamburg-hub": frozenset({TransportMode.ROAD, TransportMode.RAIL}),
        "los-angeles-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "long-beach-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "new-york-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "chicago-rail": frozenset({TransportMode.RAIL, TransportMode.ROAD}),
        "houston-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "toronto-rail": frozenset({TransportMode.RAIL, TransportMode.ROAD}),
        "sydney-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "santos-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
    }
    raw_locations = (
        ("shanghai-hub", "Shanghai", LocationKind.MULTIMODAL_HUB, "CN", "China", "East Asia", "Asia/Shanghai", 31.2304, 121.4737),
        ("shanghai-port", "Port of Shanghai", LocationKind.PORT, "CN", "China", "East Asia", "Asia/Shanghai", 31.3547, 121.6247),
        ("shanghai-airport", "Shanghai Pudong Airport", LocationKind.AIRPORT, "CN", "China", "East Asia", "Asia/Shanghai", 31.1443, 121.8083),
        ("shanghai-rail", "Shanghai Rail Terminal", LocationKind.RAIL_TERMINAL, "CN", "China", "East Asia", "Asia/Shanghai", 31.3760, 120.9819),
        ("shenzhen", "Shenzhen", LocationKind.PORT, "CN", "China", "East Asia", "Asia/Shanghai", 22.5431, 114.0579),
        ("hong-kong", "Hong Kong", LocationKind.PORT, "HK", "Hong Kong", "East Asia", "Asia/Hong_Kong", 22.3193, 114.1694),
        ("singapore-port", "Singapore", LocationKind.PORT, "SG", "Singapore", "Southeast Asia", "Asia/Singapore", 1.2644, 103.8220),
        ("colombo-port", "Colombo", LocationKind.PORT, "LK", "Sri Lanka", "South Asia", "Asia/Colombo", 6.9271, 79.8612),
        ("mumbai-port", "Mumbai", LocationKind.PORT, "IN", "India", "South Asia", "Asia/Kolkata", 18.9388, 72.8354),
        ("mumbai-airport", "Mumbai Airport", LocationKind.AIRPORT, "IN", "India", "South Asia", "Asia/Kolkata", 19.0896, 72.8656),
        ("chennai", "Chennai", LocationKind.PORT, "IN", "India", "South Asia", "Asia/Kolkata", 13.0827, 80.2707),
        ("delhi-rail", "Delhi Rail Terminal", LocationKind.RAIL_TERMINAL, "IN", "India", "South Asia", "Asia/Kolkata", 28.6139, 77.2090),
        ("dubai", "Dubai", LocationKind.CITY, "AE", "United Arab Emirates", "Middle East", "Asia/Dubai", 25.2048, 55.2708),
        ("jebel-ali", "Jebel Ali Port", LocationKind.PORT, "AE", "United Arab Emirates", "Middle East", "Asia/Dubai", 24.9857, 55.0273),
        ("durban-port", "Durban", LocationKind.PORT, "ZA", "South Africa", "Southern Africa", "Africa/Johannesburg", -29.8587, 31.0218),
        ("rotterdam-port", "Rotterdam Port", LocationKind.PORT, "NL", "Netherlands", "Western Europe", "Europe/Amsterdam", 51.9244, 4.4777),
        ("rotterdam-hub", "Rotterdam Logistics Hub", LocationKind.MULTIMODAL_HUB, "NL", "Netherlands", "Western Europe", "Europe/Amsterdam", 51.9225, 4.4792),
        ("hamburg-port", "Hamburg Port", LocationKind.PORT, "DE", "Germany", "Western Europe", "Europe/Berlin", 53.5400, 9.9860),
        ("hamburg-hub", "Hamburg Distribution Centre", LocationKind.WAREHOUSE, "DE", "Germany", "Western Europe", "Europe/Berlin", 53.5511, 9.9937),
        ("antwerp", "Antwerp", LocationKind.PORT, "BE", "Belgium", "Western Europe", "Europe/Brussels", 51.2194, 4.4025),
        ("london", "London", LocationKind.CITY, "GB", "United Kingdom", "Western Europe", "Europe/London", 51.5072, -0.1276),
        ("frankfurt-airport", "Frankfurt Airport", LocationKind.AIRPORT, "DE", "Germany", "Western Europe", "Europe/Berlin", 50.0379, 8.5622),
        ("frankfurt-rail", "Frankfurt Rail Terminal", LocationKind.RAIL_TERMINAL, "DE", "Germany", "Western Europe", "Europe/Berlin", 50.1071, 8.6638),
        ("paris", "Paris", LocationKind.RAIL_TERMINAL, "FR", "France", "Western Europe", "Europe/Paris", 48.8566, 2.3522),
        ("los-angeles-port", "Los Angeles", LocationKind.PORT, "US", "United States", "North America", "America/Los_Angeles", 33.7405, -118.2720),
        ("long-beach-port", "Long Beach", LocationKind.PORT, "US", "United States", "North America", "America/Los_Angeles", 33.7542, -118.2165),
        ("new-york-port", "New York", LocationKind.PORT, "US", "United States", "North America", "America/New_York", 40.6892, -74.0445),
        ("chicago-rail", "Chicago Rail Terminal", LocationKind.RAIL_TERMINAL, "US", "United States", "North America", "America/Chicago", 41.8781, -87.6298),
        ("houston-port", "Houston", LocationKind.PORT, "US", "United States", "North America", "America/Chicago", 29.7604, -95.3698),
        ("toronto-rail", "Toronto Rail Terminal", LocationKind.RAIL_TERMINAL, "CA", "Canada", "North America", "America/Toronto", 43.6532, -79.3832),
        ("santos-port", "Santos", LocationKind.PORT, "BR", "Brazil", "South America", "America/Sao_Paulo", -23.9608, -46.3336),
        ("sydney-port", "Sydney", LocationKind.PORT, "AU", "Australia", "Oceania", "Australia/Sydney", -33.8688, 151.2093),
    )
    locations = {
        item[0]: Location(
            id=item[0],
            kind=item[2],
            country_code=item[3],
            country_name=item[4],
            region=item[5],
            timezone=item[6],
            latitude=item[7],
            longitude=item[8],
            transfer_modes=modes.get(item[0], frozenset()),
        )
        for item in raw_locations
    }

    def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
        lat1, lon1 = radians(a[0]), radians(a[1])
        lat2, lon2 = radians(b[0]), radians(b[1])
        value = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
        return 6371.0088 * 2 * asin(sqrt(value))

    raw_links = (
        ("road-shanghai-port", "shanghai-hub", "shanghai-port", TransportMode.ROAD, 30, 3, 1, 0.3, 0.05, ()),
        ("road-shanghai-airport", "shanghai-hub", "shanghai-airport", TransportMode.ROAD, 25, 5, 1, 0.4, 0.05, ()),
        ("road-shanghai-rail", "shanghai-hub", "shanghai-rail", TransportMode.ROAD, 30, 4, 1, 0.3, 0.05, ()),
        ("sea-shanghai-singapore", "shanghai-port", "singapore-port", TransportMode.SEA, 10, 35, 7, 5, 0.12, ((25.0, 120.0), (12.5, 116.0), (1.3, 104.0))),
        ("sea-shanghai-hong-kong", "shanghai-port", "hong-kong", TransportMode.SEA, 12, 18, 3, 2, 0.08, ()),
        ("sea-hong-kong-singapore", "hong-kong", "singapore-port", TransportMode.SEA, 10, 22, 4, 2.5, 0.08, ()),
        ("sea-singapore-colombo", "singapore-port", "colombo-port", TransportMode.SEA, 8, 22, 4, 2.8, 0.08, ((5.0, 90.0),)),
        ("sea-colombo-mumbai", "colombo-port", "mumbai-port", TransportMode.SEA, 8, 18, 3, 1.8, 0.08, ()),
        ("sea-mumbai-jebel-ali", "mumbai-port", "jebel-ali", TransportMode.SEA, 8, 23, 4, 2.2, 0.1, ((20.0, 65.0),)),
        ("sea-jebel-rotterdam", "jebel-ali", "rotterdam-port", TransportMode.SEA, 8, 45, 9, 4.5, 0.18, ((20.0, 58.0), (12.0, 44.0), (12.5, 43.5), (30.0, 32.5), (35.0, 18.0), (40.0, 5.0))),
        ("sea-jebel-durban", "jebel-ali", "durban-port", TransportMode.SEA, 8, 55, 10, 6.5, 0.25, ((-5.0, 55.0), (-20.0, 45.0))),
        ("sea-durban-rotterdam", "durban-port", "rotterdam-port", TransportMode.SEA, 8, 65, 12, 7.5, 0.3, ((-34.0, 18.0), (-30.0, 0.0), (-10.0, -15.0), (10.0, -16.0), (30.0, -10.0), (45.0, -3.0))),
        ("sea-rotterdam-hamburg", "rotterdam-port", "hamburg-port", TransportMode.SEA, 6, 14, 3, 1.8, 0.2, ()),
        ("road-rotterdam-hub", "rotterdam-port", "rotterdam-hub", TransportMode.ROAD, 10, 2, 1, 0.2, 0.03, ()),
        ("road-hamburg-hub", "hamburg-port", "hamburg-hub", TransportMode.ROAD, 10, 2, 1, 0.2, 0.03, ()),
        ("road-hub-hamburg", "rotterdam-hub", "hamburg-hub", TransportMode.ROAD, 5, 10, 2, 0.7, 0.1, ()),
        ("rail-hub-hamburg", "rotterdam-hub", "hamburg-hub", TransportMode.RAIL, 5, 8, 2, 0.45, 0.08, ()),
        ("rail-shanghai-delhi", "shanghai-rail", "delhi-rail", TransportMode.RAIL, 6, 60, 15, 12, 0.35, ((40.0, 90.0), (44.0, 75.0), (40.0, 60.0), (35.0, 50.0))),
        ("rail-delhi-frankfurt", "delhi-rail", "frankfurt-rail", TransportMode.RAIL, 6, 75, 18, 14, 0.4, ((35.0, 55.0), (40.0, 45.0), (45.0, 30.0), (48.0, 15.0))),
        ("rail-frankfurt-rotterdam", "frankfurt-rail", "rotterdam-hub", TransportMode.RAIL, 6, 18, 4, 2, 0.15, ()),
        ("air-shanghai-frankfurt", "shanghai-airport", "frankfurt-airport", TransportMode.AIR, 5, 250, 90, 10, 0.75, ((45.0, 145.0), (60.0, 100.0), (60.0, 40.0))),
        ("road-frankfurt-rotterdam", "frankfurt-airport", "rotterdam-hub", TransportMode.ROAD, 8, 8, 2, 0.5, 0.08, ()),
        ("rail-frankfurt-hamburg", "frankfurt-rail", "hamburg-hub", TransportMode.RAIL, 8, 18, 4, 2, 0.1, ()),
        ("road-shenzhen-hong-kong", "shenzhen", "hong-kong", TransportMode.ROAD, 5, 2, 1, 0.2, 0.05, ()),
        ("road-hong-kong-shenzhen", "hong-kong", "shenzhen", TransportMode.ROAD, 5, 2, 1, 0.2, 0.05, ()),
        ("road-dubai-jebel-ali", "dubai", "jebel-ali", TransportMode.ROAD, 8, 2, 1, 0.2, 0.05, ()),
        ("road-jebel-ali-dubai", "jebel-ali", "dubai", TransportMode.ROAD, 8, 2, 1, 0.2, 0.05, ()),
        ("road-chicago-houston", "chicago-rail", "houston-port", TransportMode.ROAD, 3, 13, 3, 1.3, 0.12, ((37.0, -96.0),)),
        ("sea-mumbai-chennai", "mumbai-port", "chennai", TransportMode.SEA, 4, 15, 3, 1.7, 0.3, ()),
        ("road-mumbai-airport", "mumbai-port", "mumbai-airport", TransportMode.ROAD, 6, 2, 1, 0.2, 0.05, ()),
        ("air-mumbai-frankfurt", "mumbai-airport", "frankfurt-airport", TransportMode.AIR, 4, 190, 75, 8, 0.75, ((28.0, 65.0), (35.0, 45.0), (45.0, 25.0))),
        ("sea-rotterdam-antwerp", "rotterdam-port", "antwerp", TransportMode.SEA, 3, 6, 2, 0.4, 0.1, ()),
        ("rail-rotterdam-paris", "rotterdam-hub", "paris", TransportMode.RAIL, 4, 12, 3, 0.6, 0.12, ()),
        ("rail-paris-london", "paris", "london", TransportMode.RAIL, 4, 8, 2, 0.4, 0.1, ()),
        ("sea-shanghai-los-angeles", "shanghai-port", "los-angeles-port", TransportMode.SEA, 6, 50, 10, 6.0, 0.4, ((35.0, 150.0), (38.0, 175.0), (35.0, -150.0))),
        ("sea-los-angeles-long-beach", "los-angeles-port", "long-beach-port", TransportMode.SEA, 4, 2, 1, 0.2, 0.05, ()),
        ("rail-los-angeles-chicago", "los-angeles-port", "chicago-rail", TransportMode.RAIL, 4, 24, 5, 2.1, 0.2, ((39.0, -110.0), (40.0, -100.0))),
        ("road-chicago-new-york", "chicago-rail", "new-york-port", TransportMode.ROAD, 3, 12, 3, 1.2, 0.12, ()),
        ("rail-chicago-toronto", "chicago-rail", "toronto-rail", TransportMode.RAIL, 3, 9, 2, 0.7, 0.1, ()),
        ("sea-houston-santos", "houston-port", "santos-port", TransportMode.SEA, 3, 28, 6, 3.2, 0.3, ()),
        ("sea-santos-durban", "santos-port", "durban-port", TransportMode.SEA, 3, 38, 8, 4.1, 0.3, ()),
        ("sea-singapore-sydney", "singapore-port", "sydney-port", TransportMode.SEA, 3, 34, 7, 3.7, 0.3, ()),
    )
    links: list[TransportLink] = []
    synthetic_carbon_intensity = {
        TransportMode.ROAD: 0.4,
        TransportMode.RAIL: 2.5,
        TransportMode.SEA: 0.8,
        TransportMode.AIR: 8.0,
    }
    for link_id, origin, destination, mode, capacity, fixed, variable, days, exposure, waypoints in raw_links:
        origin_location = locations[origin]
        destination_location = locations[destination]
        assert origin_location.latitude is not None and destination_location.latitude is not None
        geometry = (
            (origin_location.latitude, origin_location.longitude),
            *waypoints,
            (destination_location.latitude, destination_location.longitude),
        )
        distance = sum(haversine(geometry[index], geometry[index + 1]) for index in range(len(geometry) - 1))
        links.append(
            TransportLink(
                id=link_id,
                origin_id=origin,
                destination_id=destination,
                mode=mode,
                capacity=capacity,
                capacity_unit="load_unit",
                fixed_cost=fixed,
                variable_cost_per_quantity_unit=variable,
                transit_time=days,
                carbon_per_quantity_unit=synthetic_carbon_intensity[mode],
                distance_km=round(distance * (1.08 if mode is not TransportMode.AIR else 1.03), 1),
                geometry=geometry,
                resilience_exposure=exposure,
            )
        )
    return TransportationNetwork(
        locations=MappingProxyType(locations),
        links=tuple(links),
        quantity_unit="load_unit",
        cost_unit="synthetic_cost_unit",
        time_unit="day",
        carbon_unit="kgCO2e",
    )


@lru_cache(maxsize=1)
def global_demo_shipments() -> tuple[ShipmentProfile, ...]:
    """Return deterministic example shipments with disclosed synthetic inputs."""
    departure = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return (
        ShipmentProfile(
            request=ShipmentRequest(
                id="EXP-104",
                origin_id="shanghai-hub",
                destination_id="rotterdam-hub",
                quantity=2,
                quantity_unit="load_unit",
                deadline=24,
                deadline_unit="day",
            ),
            cargo_category="Electronics",
            priority=5,
            delay_penalty_per_day=18,
            maximum_transit_time=60,
            departure_time=departure,
        ),
        ShipmentProfile(
            request=ShipmentRequest(
                id="EXP-205",
                origin_id="shanghai-hub",
                destination_id="hamburg-hub",
                quantity=2,
                quantity_unit="load_unit",
                deadline=29,
                deadline_unit="day",
            ),
            cargo_category="Industrial components",
            priority=3,
            delay_penalty_per_day=12,
            maximum_transit_time=65,
            departure_time=departure,
        ),
    )


@lru_cache(maxsize=1)
def global_demo_scenario() -> DisruptionScenario:
    """A synthetic Suez capacity restriction, not a live corridor alert."""
    network = global_demo_network()
    scenario = DisruptionScenario(
        id="synthetic-suez-capacity-restriction",
        capacity_overrides={"sea-jebel-rotterdam": 3},
        cost_multipliers={"sea-jebel-rotterdam": 1.2},
    )
    scenario.validate_for(network)
    return scenario
