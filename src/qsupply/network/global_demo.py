"""Deterministic synthetic global network and shipment scenario for demos."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class GlobalDemoScenario:
    """Reproducible synthetic business example exposed through the demo API."""

    id: str
    name: str
    business_problem: str
    shipment_ids: tuple[str, ...]
    scenario_id: str | None
    constraints: tuple[str, ...]
    alternatives: tuple[str, ...]


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
        "hong-kong": frozenset({TransportMode.SEA, TransportMode.ROAD}),
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
    # Curated gateway additions are data records, so adding a region does not
    # require routing-engine changes. All values remain illustrative.
    raw_locations += (
        ("beijing-airport", "Beijing Capital Airport", LocationKind.AIRPORT, "CN", "China", "East Asia", "Asia/Shanghai", 40.0799, 116.6031),
        ("guangzhou-port", "Port of Guangzhou", LocationKind.PORT, "CN", "China", "East Asia", "Asia/Shanghai", 23.0930, 113.4500),
        ("tokyo-port", "Port of Tokyo", LocationKind.PORT, "JP", "Japan", "East Asia", "Asia/Tokyo", 35.6167, 139.7667),
        ("tokyo-airport", "Tokyo Haneda Airport", LocationKind.AIRPORT, "JP", "Japan", "East Asia", "Asia/Tokyo", 35.5494, 139.7798),
        ("osaka-port", "Port of Osaka", LocationKind.PORT, "JP", "Japan", "East Asia", "Asia/Tokyo", 34.6537, 135.4289),
        ("busan-port", "Port of Busan", LocationKind.PORT, "KR", "South Korea", "East Asia", "Asia/Seoul", 35.1028, 129.0403),
        ("seoul-airport", "Incheon Airport", LocationKind.AIRPORT, "KR", "South Korea", "East Asia", "Asia/Seoul", 37.4602, 126.4407),
        ("bangkok-hub", "Bangkok Logistics Hub", LocationKind.MULTIMODAL_HUB, "TH", "Thailand", "Southeast Asia", "Asia/Bangkok", 13.7563, 100.5018),
        ("port-klang", "Port Klang", LocationKind.PORT, "MY", "Malaysia", "Southeast Asia", "Asia/Kuala_Lumpur", 3.0000, 101.4000),
        ("ho-chi-minh-port", "Cat Lai Port, Ho Chi Minh City", LocationKind.PORT, "VN", "Vietnam", "Southeast Asia", "Asia/Ho_Chi_Minh", 10.7697, 106.7820),
        ("jakarta-port", "Tanjung Priok Port", LocationKind.PORT, "ID", "Indonesia", "Southeast Asia", "Asia/Jakarta", -6.1040, 106.8800),
        ("chittagong-port", "Chattogram Port", LocationKind.PORT, "BD", "Bangladesh", "South Asia", "Asia/Dhaka", 22.3106, 91.8000),
        ("delhi-airport", "Delhi Airport", LocationKind.AIRPORT, "IN", "India", "South Asia", "Asia/Kolkata", 28.5562, 77.1000),
        ("bengaluru-hub", "Bengaluru Distribution Hub", LocationKind.WAREHOUSE, "IN", "India", "South Asia", "Asia/Kolkata", 12.9716, 77.5946),
        ("doha-airport", "Hamad International Airport", LocationKind.AIRPORT, "QA", "Qatar", "Middle East", "Asia/Qatar", 25.2731, 51.6081),
        ("muscat-port", "Port Sultan Qaboos", LocationKind.PORT, "OM", "Oman", "Middle East", "Asia/Muscat", 23.6267, 58.5633),
        ("riyadh-hub", "Riyadh Logistics Hub", LocationKind.MULTIMODAL_HUB, "SA", "Saudi Arabia", "Middle East", "Asia/Riyadh", 24.7136, 46.6753),
        ("moscow-rail", "Moscow Rail Freight Terminal", LocationKind.RAIL_TERMINAL, "RU", "Russia", "Russia and Eurasia", "Europe/Moscow", 55.7558, 37.6173),
        ("almaty-rail", "Almaty Rail Freight Terminal", LocationKind.RAIL_TERMINAL, "KZ", "Kazakhstan", "Russia and Eurasia", "Asia/Almaty", 43.2383, 76.9450),
        ("istanbul-hub", "Istanbul Intermodal Hub", LocationKind.MULTIMODAL_HUB, "TR", "Türkiye", "Middle East", "Europe/Istanbul", 41.0082, 28.9784),
        ("milan-hub", "Milan Logistics Hub", LocationKind.MULTIMODAL_HUB, "IT", "Italy", "Southern Europe", "Europe/Rome", 45.4642, 9.1900),
        ("madrid-hub", "Madrid Logistics Hub", LocationKind.MULTIMODAL_HUB, "ES", "Spain", "Southern Europe", "Europe/Madrid", 40.4168, -3.7038),
        ("warsaw-rail", "Warsaw Rail Terminal", LocationKind.RAIL_TERMINAL, "PL", "Poland", "Central Europe", "Europe/Warsaw", 52.2297, 21.0122),
        ("felixstowe-port", "Port of Felixstowe", LocationKind.PORT, "GB", "United Kingdom", "Western Europe", "Europe/London", 51.9540, 1.3510),
        ("barcelona-port", "Port of Barcelona", LocationKind.PORT, "ES", "Spain", "Southern Europe", "Europe/Madrid", 41.3502, 2.1580),
        ("vancouver-port", "Port of Vancouver", LocationKind.PORT, "CA", "Canada", "North America", "America/Vancouver", 49.2827, -123.1207),
        ("seattle-port", "Port of Seattle", LocationKind.PORT, "US", "United States", "North America", "America/Los_Angeles", 47.6062, -122.3321),
        ("montreal-port", "Port of Montreal", LocationKind.PORT, "CA", "Canada", "North America", "America/Toronto", 45.5019, -73.5674),
        ("los-angeles-airport", "Los Angeles International Airport", LocationKind.AIRPORT, "US", "United States", "North America", "America/Los_Angeles", 33.9416, -118.4085),
        ("new-york-airport", "John F. Kennedy International Airport", LocationKind.AIRPORT, "US", "United States", "North America", "America/New_York", 40.6413, -73.7781),
        ("manzanillo-port", "Port of Manzanillo", LocationKind.PORT, "MX", "Mexico", "North America", "America/Mexico_City", 19.0522, -104.3157),
        ("mexico-city-hub", "Mexico City Distribution Hub", LocationKind.WAREHOUSE, "MX", "Mexico", "North America", "America/Mexico_City", 19.4326, -99.1332),
        ("buenos-aires-port", "Port of Buenos Aires", LocationKind.PORT, "AR", "Argentina", "South America", "America/Argentina/Buenos_Aires", -34.6037, -58.3816),
        ("santiago-hub", "Santiago Logistics Hub", LocationKind.MULTIMODAL_HUB, "CL", "Chile", "South America", "America/Santiago", -33.4489, -70.6693),
        ("callao-port", "Port of Callao", LocationKind.PORT, "PE", "Peru", "South America", "America/Lima", -12.0464, -77.1428),
        ("melbourne-port", "Port of Melbourne", LocationKind.PORT, "AU", "Australia", "Oceania", "Australia/Melbourne", -37.8136, 144.9631),
        ("auckland-port", "Port of Auckland", LocationKind.PORT, "NZ", "New Zealand", "Oceania", "Pacific/Auckland", -36.8485, 174.7633),
        ("singapore-airport", "Singapore Changi Airport", LocationKind.AIRPORT, "SG", "Singapore", "Southeast Asia", "Asia/Singapore", 1.3644, 103.9915),
        ("sydney-airport", "Sydney Kingsford Smith Airport", LocationKind.AIRPORT, "AU", "Australia", "Oceania", "Australia/Sydney", -33.9399, 151.1753),
        ("dubai-airport", "Dubai International Airport", LocationKind.AIRPORT, "AE", "United Arab Emirates", "Middle East", "Asia/Dubai", 25.2532, 55.3657),
        ("sao-paulo-airport", "São Paulo Guarulhos Airport", LocationKind.AIRPORT, "BR", "Brazil", "South America", "America/Sao_Paulo", -23.4356, -46.4731),
        ("santiago-airport", "Santiago Airport", LocationKind.AIRPORT, "CL", "Chile", "South America", "America/Santiago", -33.3930, -70.7858),
    )
    modes.update({
        "tokyo-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "tokyo-airport": frozenset({TransportMode.AIR, TransportMode.ROAD}),
        "busan-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "seoul-airport": frozenset({TransportMode.AIR, TransportMode.ROAD}),
        "bangkok-hub": all_modes,
        "port-klang": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "ho-chi-minh-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "jakarta-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "chittagong-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "delhi-airport": frozenset({TransportMode.AIR, TransportMode.ROAD}),
        "bengaluru-hub": frozenset({TransportMode.ROAD, TransportMode.RAIL}),
        "doha-airport": frozenset({TransportMode.AIR, TransportMode.ROAD}),
        "muscat-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "riyadh-hub": frozenset({TransportMode.ROAD, TransportMode.RAIL}),
        "moscow-rail": frozenset({TransportMode.RAIL, TransportMode.ROAD}),
        "almaty-rail": frozenset({TransportMode.RAIL, TransportMode.ROAD}),
        "istanbul-hub": all_modes,
        "milan-hub": frozenset({TransportMode.RAIL, TransportMode.ROAD}),
        "madrid-hub": frozenset({TransportMode.RAIL, TransportMode.ROAD}),
        "warsaw-rail": frozenset({TransportMode.RAIL, TransportMode.ROAD}),
        "vancouver-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "montreal-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "manzanillo-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "mexico-city-hub": frozenset({TransportMode.ROAD, TransportMode.RAIL}),
        "buenos-aires-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "santiago-hub": frozenset({TransportMode.ROAD, TransportMode.RAIL}),
        "callao-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "melbourne-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "auckland-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "barcelona-port": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "los-angeles-airport": frozenset({TransportMode.AIR, TransportMode.ROAD, TransportMode.RAIL}),
        "new-york-airport": frozenset({TransportMode.AIR, TransportMode.ROAD}),
        "singapore-airport": frozenset({TransportMode.AIR, TransportMode.ROAD}),
        "sydney-airport": frozenset({TransportMode.AIR, TransportMode.ROAD}),
        "dubai-airport": frozenset({TransportMode.AIR, TransportMode.ROAD}),
        "sao-paulo-airport": frozenset({TransportMode.AIR, TransportMode.ROAD}),
        "santiago-airport": frozenset({TransportMode.AIR, TransportMode.ROAD}),
        # Existing gateways that are now used for additional intermodal paths.
        "mumbai-port": frozenset({TransportMode.SEA, TransportMode.ROAD, TransportMode.RAIL}),
        "chennai": frozenset({TransportMode.SEA, TransportMode.ROAD}),
        "los-angeles-port": frozenset({TransportMode.SEA, TransportMode.ROAD, TransportMode.RAIL}),
        "vancouver-port": frozenset({TransportMode.SEA, TransportMode.ROAD, TransportMode.RAIL}),
        "seattle-port": frozenset({TransportMode.SEA, TransportMode.ROAD, TransportMode.RAIL}),
        "paris": frozenset({TransportMode.RAIL, TransportMode.ROAD}),
        "london": frozenset({TransportMode.RAIL, TransportMode.ROAD}),
    })
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
    raw_links += (
        # East and Southeast Asia gateway alternatives.
        ("sea-shanghai-tokyo", "shanghai-port", "tokyo-port", TransportMode.SEA, 8, 18, 4, 2.4, 0.12, ()),
        ("sea-shanghai-busan", "shanghai-port", "busan-port", TransportMode.SEA, 8, 16, 4, 2.2, 0.12, ()),
        ("sea-busan-tokyo", "busan-port", "tokyo-port", TransportMode.SEA, 6, 12, 3, 1.8, 0.1, ()),
        ("sea-singapore-port-klang", "singapore-port", "port-klang", TransportMode.SEA, 8, 8, 2, 1.1, 0.08, ()),
        ("sea-singapore-ho-chi-minh", "singapore-port", "ho-chi-minh-port", TransportMode.SEA, 7, 12, 3, 1.7, 0.1, ()),
        ("sea-port-klang-jakarta", "port-klang", "jakarta-port", TransportMode.SEA, 6, 15, 3, 2.0, 0.12, ()),
        ("sea-chennai-chittagong", "chennai", "chittagong-port", TransportMode.SEA, 5, 20, 4, 2.5, 0.15, ()),
        ("road-bangkok-ho-chi-minh", "bangkok-hub", "ho-chi-minh-port", TransportMode.ROAD, 4, 16, 3, 2.0, 0.1, ((13.7, 104.9),)),
        ("road-bangkok-port-klang", "bangkok-hub", "port-klang", TransportMode.ROAD, 3, 20, 4, 2.4, 0.12, ((7.0, 100.5),)),
        ("road-shanghai-beijing", "shanghai-hub", "beijing-airport", TransportMode.ROAD, 5, 10, 2, 1.1, 0.08, ((35.0, 115.0),)),
        ("road-mumbai-delhi-airport", "mumbai-port", "delhi-airport", TransportMode.ROAD, 4, 15, 3, 1.8, 0.1, ((23.0, 75.0),)),
        ("road-delhi-airport-rail", "delhi-airport", "delhi-rail", TransportMode.ROAD, 4, 2, 1, 0.25, 0.04, ()),
        ("rail-delhi-bengaluru", "delhi-rail", "bengaluru-hub", TransportMode.RAIL, 6, 28, 5, 3.0, 0.12, ((21.0, 78.0),)),
        ("road-bengaluru-chennai", "bengaluru-hub", "chennai", TransportMode.ROAD, 6, 8, 2, 0.9, 0.07, ()),
        ("air-delhi-doha", "delhi-airport", "doha-airport", TransportMode.AIR, 4, 110, 35, 5.0, 0.55, ((27.0, 65.0),)),
        # Middle East regional gateways and cross-border alternatives.
        ("sea-jebel-muscat", "jebel-ali", "muscat-port", TransportMode.SEA, 5, 12, 3, 1.6, 0.1, ()),
        ("road-dubai-riyadh", "dubai", "riyadh-hub", TransportMode.ROAD, 4, 20, 4, 2.0, 0.12, ()),
        ("rail-riyadh-jebel", "riyadh-hub", "jebel-ali", TransportMode.RAIL, 4, 18, 3, 1.9, 0.12, ()),
        ("air-mumbai-doha", "mumbai-airport", "doha-airport", TransportMode.AIR, 4, 100, 32, 4.2, 0.5, ((22.0, 62.0),)),
        ("air-doha-frankfurt", "doha-airport", "frankfurt-airport", TransportMode.AIR, 4, 140, 46, 6.0, 0.6, ((35.0, 45.0),)),
        # Eurasian rail is explicitly a modeled corridor, not an assertion of
        # unrestricted current service or border clearance.
        ("rail-shanghai-almaty", "shanghai-rail", "almaty-rail", TransportMode.RAIL, 4, 48, 12, 10, 0.35, ((42.0, 95.0), (43.0, 82.0))),
        ("rail-almaty-moscow", "almaty-rail", "moscow-rail", TransportMode.RAIL, 3, 70, 18, 14, 0.45, ((48.0, 65.0), (52.0, 48.0))),
        ("rail-almaty-istanbul", "almaty-rail", "istanbul-hub", TransportMode.RAIL, 3, 85, 22, 18, 0.5, ((40.0, 60.0), (39.0, 45.0), (40.0, 35.0))),
        # Europe: port, air and inland rail/road connections.
        ("rail-rotterdam-warsaw", "rotterdam-hub", "warsaw-rail", TransportMode.RAIL, 5, 30, 6, 4.0, 0.14, ((52.0, 10.0),)),
        ("rail-warsaw-hamburg", "warsaw-rail", "hamburg-hub", TransportMode.RAIL, 5, 18, 4, 2.5, 0.1, ()),
        ("rail-hamburg-milan", "hamburg-hub", "milan-hub", TransportMode.RAIL, 4, 28, 5, 3.5, 0.12, ((48.0, 11.0),)),
        ("rail-milan-paris", "milan-hub", "paris", TransportMode.RAIL, 4, 16, 3, 2.0, 0.1, ()),
        ("rail-paris-madrid", "paris", "madrid-hub", TransportMode.RAIL, 4, 24, 5, 3.0, 0.12, ((43.0, 2.0),)),
        ("road-madrid-barcelona", "madrid-hub", "barcelona-port", TransportMode.ROAD, 3, 28, 6, 3.0, 0.15, ((41.0, 0.0),)),
        ("sea-rotterdam-felixstowe", "rotterdam-port", "felixstowe-port", TransportMode.SEA, 4, 10, 2, 1.5, 0.08, ()),
        ("road-felixstowe-london", "felixstowe-port", "london", TransportMode.ROAD, 4, 8, 2, 0.8, 0.06, ()),
        # North American inland and coastal corridors.
        ("rail-chicago-vancouver", "chicago-rail", "vancouver-port", TransportMode.RAIL, 4, 35, 7, 4.5, 0.2, ((46.0, -112.0),)),
        ("rail-chicago-montreal", "chicago-rail", "montreal-port", TransportMode.RAIL, 4, 24, 5, 3.2, 0.14, ()),
        ("sea-shanghai-new-york", "shanghai-port", "new-york-port", TransportMode.SEA, 5, 62, 12, 7.5, 0.42, ((35.0, 150.0), (48.0, 170.0), (55.0, -160.0), (48.0, -130.0), (40.0, -120.0), (35.0, -75.0))),
        ("sea-rotterdam-new-york", "rotterdam-port", "new-york-port", TransportMode.SEA, 5, 45, 9, 5.5, 0.3, ((52.0, -10.0), (45.0, -35.0), (42.0, -65.0))),
        ("air-shanghai-los-angeles", "shanghai-airport", "los-angeles-airport", TransportMode.AIR, 4, 200, 70, 8, 0.65, ((42.0, 160.0), (48.0, -170.0), (40.0, -130.0))),
        ("air-frankfurt-new-york", "frankfurt-airport", "new-york-airport", TransportMode.AIR, 4, 180, 60, 7, 0.65, ((55.0, -20.0), (50.0, -50.0))),
        ("road-los-angeles-mexico-city", "los-angeles-port", "mexico-city-hub", TransportMode.ROAD, 3, 30, 6, 3.5, 0.18, ((27.0, -110.0), (25.0, -105.0))),
        ("road-manzanillo-mexico-city", "manzanillo-port", "mexico-city-hub", TransportMode.ROAD, 4, 18, 4, 2.0, 0.12, ()),
        ("sea-houston-manzanillo", "houston-port", "manzanillo-port", TransportMode.SEA, 3, 24, 5, 3.0, 0.2, ((20.0, -95.0),)),
        # South America and Pacific connections.
        ("sea-los-angeles-callao", "los-angeles-port", "callao-port", TransportMode.SEA, 3, 40, 8, 5.5, 0.3, ((10.0, -110.0), (0.0, -90.0))),
        ("sea-callao-santos", "callao-port", "santos-port", TransportMode.SEA, 3, 42, 8, 6.0, 0.32, ((-20.0, -80.0), (-35.0, -65.0))),
        ("sea-santos-buenos-aires", "santos-port", "buenos-aires-port", TransportMode.SEA, 3, 20, 4, 2.5, 0.16, ()),
        ("road-buenos-aires-santiago", "buenos-aires-port", "santiago-hub", TransportMode.ROAD, 2, 32, 7, 4.0, 0.2, ((-34.0, -68.0),)),
        ("air-sao-paulo-santiago", "sao-paulo-airport", "santiago-airport", TransportMode.AIR, 2, 55, 18, 2.0, 0.45, ()),
        # Oceania and Southeast Asia alternatives.
        ("sea-jakarta-sydney", "jakarta-port", "sydney-port", TransportMode.SEA, 3, 32, 6, 4.0, 0.25, ((-12.0, 118.0),)),
        ("sea-melbourne-auckland", "melbourne-port", "auckland-port", TransportMode.SEA, 3, 25, 5, 3.0, 0.18, ()),
        ("air-singapore-sydney", "singapore-airport", "sydney-airport", TransportMode.AIR, 3, 100, 34, 2.8, 0.5, ((-10.0, 130.0),)),
        ("air-tokyo-sydney", "tokyo-airport", "sydney-airport", TransportMode.AIR, 3, 120, 40, 3.4, 0.55, ((10.0, 145.0),)),
        ("air-shanghai-tokyo", "shanghai-airport", "tokyo-airport", TransportMode.AIR, 4, 100, 32, 2.5, 0.5, ((40.0, 145.0),)),
        ("road-tokyo-airport-port", "tokyo-airport", "tokyo-port", TransportMode.ROAD, 4, 3, 1, 0.25, 0.05, ()),
        ("road-singapore-port-airport", "singapore-port", "singapore-airport", TransportMode.ROAD, 4, 3, 1, 0.25, 0.05, ()),
        ("road-sydney-airport-port", "sydney-airport", "sydney-port", TransportMode.ROAD, 4, 3, 1, 0.25, 0.05, ()),
        ("road-dubai-airport-jebel", "dubai-airport", "jebel-ali", TransportMode.ROAD, 4, 3, 1, 0.25, 0.05, ()),
        ("air-mumbai-dubai", "mumbai-airport", "dubai-airport", TransportMode.AIR, 4, 90, 30, 3.5, 0.48, ()),
        ("road-frankfurt-airport-rail", "frankfurt-airport", "frankfurt-rail", TransportMode.ROAD, 5, 3, 1, 0.25, 0.04, ()),
        ("road-frankfurt-rail-airport", "frankfurt-rail", "frankfurt-airport", TransportMode.ROAD, 5, 3, 1, 0.25, 0.04, ()),
        ("road-rotterdam-hub-port", "rotterdam-hub", "rotterdam-port", TransportMode.ROAD, 5, 2, 1, 0.2, 0.03, ()),
        ("rail-rotterdam-frankfurt", "rotterdam-hub", "frankfurt-rail", TransportMode.RAIL, 4, 20, 4, 2.7, 0.12, ()),
        ("road-los-angeles-airport-port", "los-angeles-airport", "los-angeles-port", TransportMode.ROAD, 4, 3, 1, 0.25, 0.04, ()),
        ("rail-los-angeles-airport-chicago", "los-angeles-airport", "chicago-rail", TransportMode.RAIL, 4, 25, 5, 2.2, 0.2, ((39.0, -110.0), (40.0, -100.0))),
        ("road-new-york-airport-port", "new-york-airport", "new-york-port", TransportMode.ROAD, 4, 3, 1, 0.25, 0.04, ()),
        ("sea-shanghai-vancouver", "shanghai-port", "vancouver-port", TransportMode.SEA, 4, 48, 10, 6.4, 0.38, ((35.0, 150.0), (48.0, 170.0), (52.0, -150.0), (50.0, -130.0))),
        ("sea-shanghai-seattle", "shanghai-port", "seattle-port", TransportMode.SEA, 3, 46, 9, 6.0, 0.36, ((35.0, 150.0), (48.0, 170.0), (52.0, -150.0), (48.0, -130.0))),
        ("rail-seattle-chicago", "seattle-port", "chicago-rail", TransportMode.RAIL, 3, 30, 6, 3.8, 0.19, ((45.0, -115.0), (44.0, -105.0))),
        ("rail-vancouver-chicago", "vancouver-port", "chicago-rail", TransportMode.RAIL, 3, 32, 7, 4.0, 0.2, ((49.0, -115.0), (47.0, -105.0))),
        ("sea-rotterdam-barcelona", "rotterdam-port", "barcelona-port", TransportMode.SEA, 3, 22, 4, 3.0, 0.14, ((43.0, 5.0),)),
        ("road-santos-sao-paulo-airport", "santos-port", "sao-paulo-airport", TransportMode.ROAD, 3, 6, 1, 0.7, 0.05, ()),
        ("road-santiago-hub-airport", "santiago-hub", "santiago-airport", TransportMode.ROAD, 3, 3, 1, 0.25, 0.05, ()),
        ("road-santiago-airport-hub", "santiago-airport", "santiago-hub", TransportMode.ROAD, 3, 3, 1, 0.25, 0.05, ()),
        # Synthetic domestic distribution connections.
        ("rail-mumbai-delhi", "mumbai-port", "delhi-rail", TransportMode.RAIL, 5, 25, 5, 3.2, 0.12, ((23.0, 75.0),)),
    )
    raw_links += (
        ("sea-guangzhou-singapore", "guangzhou-port", "singapore-port", TransportMode.SEA, 5, 30, 6, 4.5, 0.18, ((15.0, 112.0), (8.0, 107.0))),
        ("road-shenzhen-guangzhou", "shenzhen", "guangzhou-port", TransportMode.ROAD, 4, 7, 2, 0.8, 0.06, ()),
        ("road-port-klang-bangkok", "port-klang", "bangkok-hub", TransportMode.ROAD, 4, 18, 3, 2.0, 0.1, ((10.0, 101.0),)),
        ("sea-sydney-melbourne", "sydney-port", "melbourne-port", TransportMode.SEA, 3, 12, 2, 1.5, 0.1, ()),
        ("sea-tokyo-osaka", "tokyo-port", "osaka-port", TransportMode.SEA, 4, 8, 2, 1.2, 0.08, ()),
        ("sea-osaka-busan", "osaka-port", "busan-port", TransportMode.SEA, 4, 10, 2, 1.5, 0.1, ()),
        ("air-shanghai-seoul", "shanghai-airport", "seoul-airport", TransportMode.AIR, 4, 90, 30, 2.2, 0.48, ()),
        ("road-seoul-busan", "seoul-airport", "busan-port", TransportMode.ROAD, 3, 8, 2, 0.8, 0.08, ()),
        ("road-chennai-bengaluru", "chennai", "bengaluru-hub", TransportMode.ROAD, 5, 8, 2, 0.9, 0.07, ()),
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
        ShipmentProfile(
            request=ShipmentRequest(
                id="EXP-306", origin_id="mumbai-port", destination_id="jebel-ali",
                quantity=2, quantity_unit="load_unit", deadline=7, deadline_unit="day",
            ),
            cargo_category="Pharmaceutical supplies", priority=5,
            delay_penalty_per_day=16, maximum_transit_time=30, departure_time=departure,
        ),
        ShipmentProfile(
            request=ShipmentRequest(
                id="EXP-407", origin_id="shanghai-hub", destination_id="chicago-rail",
                quantity=2, quantity_unit="load_unit", deadline=35, deadline_unit="day",
            ),
            cargo_category="Consumer electronics", priority=4,
            delay_penalty_per_day=14, maximum_transit_time=90, departure_time=departure,
        ),
        ShipmentProfile(
            request=ShipmentRequest(
                id="EXP-508", origin_id="singapore-port", destination_id="sydney-port",
                quantity=1, quantity_unit="load_unit", deadline=12, deadline_unit="day",
            ),
            cargo_category="Temperature-controlled goods", priority=4,
            delay_penalty_per_day=12, maximum_transit_time=45, departure_time=departure,
        ),
        ShipmentProfile(
            request=ShipmentRequest(
                id="EXP-609", origin_id="rotterdam-hub", destination_id="new-york-port",
                quantity=2, quantity_unit="load_unit", deadline=14, deadline_unit="day",
            ),
            cargo_category="Industrial machinery", priority=3,
            delay_penalty_per_day=10, maximum_transit_time=55, departure_time=departure,
        ),
        ShipmentProfile(
            request=ShipmentRequest(
                id="DOM-710", origin_id="mumbai-port", destination_id="bengaluru-hub",
                quantity=1, quantity_unit="load_unit", deadline=8, deadline_unit="day",
            ),
            cargo_category="Retail replenishment", priority=3,
            delay_penalty_per_day=8, maximum_transit_time=35, departure_time=departure,
        ),
    )


@lru_cache(maxsize=1)
def global_demo_disruptions() -> tuple[DisruptionScenario, ...]:
    """Curated, deterministic what-if overlays; none describe live events."""
    network = global_demo_network()
    scenarios = (
        DisruptionScenario(
            id="synthetic-suez-capacity-restriction",
            capacity_overrides={"sea-jebel-rotterdam": 3},
            cost_multipliers={"sea-jebel-rotterdam": 1.2},
        ),
        DisruptionScenario(
            id="synthetic-india-uae-combined-restriction",
            capacity_overrides={"sea-mumbai-jebel-ali": 2},
            cost_multipliers={"sea-mumbai-jebel-ali": 1.2},
            transit_time_additions={"sea-mumbai-jebel-ali": 2},
        ),
        DisruptionScenario(
            id="synthetic-china-us-port-closure",
            closed_link_ids=frozenset({"sea-shanghai-los-angeles"}),
        ),
        DisruptionScenario(
            id="synthetic-singapore-customs-delay",
            transit_time_additions={"sea-singapore-sydney": 6},
        ),
        DisruptionScenario(
            id="synthetic-transatlantic-rate-surge",
            cost_multipliers={"sea-rotterdam-new-york": 1.35},
            transit_time_multipliers={"sea-rotterdam-new-york": 1.1},
        ),
        DisruptionScenario(
            id="synthetic-india-rail-interruption",
            closed_link_ids=frozenset({"rail-mumbai-delhi"}),
            capacity_overrides={"road-mumbai-delhi-airport": 1},
        ),
        DisruptionScenario(
            id="synthetic-frankfurt-airport-disruption",
            closed_link_ids=frozenset({"air-shanghai-frankfurt"}),
        ),
        DisruptionScenario(
            id="synthetic-eurasian-rail-restriction",
            capacity_overrides={"rail-shanghai-almaty": 1},
            transit_time_additions={"rail-almaty-moscow": 3},
        ),
        DisruptionScenario(
            id="synthetic-mumbai-road-capacity-reduction",
            capacity_overrides={"road-mumbai-airport": 2},
        ),
    )
    for scenario in scenarios:
        scenario.validate_for(network)
    return scenarios


@lru_cache(maxsize=1)
def global_demo_scenarios() -> tuple[GlobalDemoScenario, ...]:
    """Six runnable business examples referencing stable shipment/scenario IDs."""
    return (
        GlobalDemoScenario(
            id="demo-china-germany",
            name="China → Germany: mode trade-off",
            business_problem="Compare ocean, air and rail-enabled options for an electronics shipment from Shanghai to a German distribution hub.",
            shipment_ids=("EXP-104",), scenario_id=None,
            constraints=("Shipment quantity: 2 load units", "Maximum transit time: 60 days", "Synthetic freight, time, capacity and carbon inputs"),
            alternatives=("Sea through Singapore and Suez-area links", "Air through Frankfurt", "Eurasian rail candidate where the path pool finds it"),
        ),
        GlobalDemoScenario(
            id="demo-india-uae",
            name="India → UAE: port versus air",
            business_problem="Compare sea freight and an air connection with last-mile road movement from Mumbai to Jebel Ali.",
            shipment_ids=("EXP-306",), scenario_id="synthetic-india-uae-combined-restriction",
            constraints=("Shipment quantity: 2 load units", "Sea link capacity reduced from 8 to 2 load units", "Synthetic two-day port delay and 20% sea cost increase"),
            alternatives=("Direct sea link", "Air via Dubai with road access to Jebel Ali"),
        ),
        GlobalDemoScenario(
            id="demo-china-usa",
            name="China → USA: port disruption recovery",
            business_problem="Route Shanghai-origin electronics to Chicago using ocean or air plus inland rail, then test a synthetic Los Angeles corridor closure.",
            shipment_ids=("EXP-407",), scenario_id="synthetic-china-us-port-closure",
            constraints=("Shipment quantity: 2 load units", "Maximum transit time: 90 days", "The direct synthetic Shanghai–Los Angeles sea link is closed"),
            alternatives=("Sea via Vancouver and inland rail", "Air to Los Angeles and inland rail"),
        ),
        GlobalDemoScenario(
            id="demo-singapore-australia",
            name="Singapore → Australia: customs delay",
            business_problem="Compare a lower-cost ocean route with air and road transfer after a synthetic customs delay is applied to the ocean corridor.",
            shipment_ids=("EXP-508",), scenario_id="synthetic-singapore-customs-delay",
            constraints=("Shipment quantity: 1 load unit", "Maximum transit time: 45 days", "Synthetic six-day additive customs delay on sea link"),
            alternatives=("Direct ocean link", "Air from Changi to Sydney with road terminal access"),
        ),
        GlobalDemoScenario(
            id="demo-europe-north-america",
            name="Europe → North America: cost, time and carbon",
            business_problem="Compare transatlantic ocean and air-plus-road alternatives for machinery shipped from Rotterdam to New York.",
            shipment_ids=("EXP-609",), scenario_id="synthetic-transatlantic-rate-surge",
            constraints=("Shipment quantity: 2 load units", "Maximum transit time: 55 days", "Synthetic ocean rate increase and transit-time multiplier"),
            alternatives=("Ocean via Rotterdam port", "Rail/road to Frankfurt then air to New York"),
        ),
        GlobalDemoScenario(
            id="demo-india-domestic",
            name="India domestic: port to inland distribution",
            business_problem="Compare rail-enabled inland movement and a coastal-plus-road alternative from Mumbai to Bengaluru.",
            shipment_ids=("DOM-710",), scenario_id="synthetic-india-rail-interruption",
            constraints=("Shipment quantity: 1 load unit", "Maximum transit time: 35 days", "Mumbai–Delhi rail link closed; selected road capacity reduced"),
            alternatives=("Rail through Delhi and onward inland rail", "Coastal sea to Chennai and road to Bengaluru"),
        ),
    )


@lru_cache(maxsize=1)
def global_demo_scenario() -> DisruptionScenario:
    """Return the legacy synthetic Suez restriction for API compatibility."""
    return global_demo_disruptions()[0]
