"""Validated multimodal network, shipment, and disruption data contracts.

All link capacities and shipment quantities use the network's declared
``quantity_unit``. A shipment of quantity ``q`` consumes ``q`` capacity units
on each traversed link. Link variable cost and carbon are per quantity unit;
fixed cost and transit time are per link traversal. Real-world capacity
conversions must be performed explicitly before constructing these models.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from numbers import Real
from types import MappingProxyType


class LocationKind(str, Enum):
    FACTORY = "factory"
    PORT = "port"
    AIRPORT = "airport"
    RAIL_TERMINAL = "rail_terminal"
    WAREHOUSE = "warehouse"
    DESTINATION = "destination"
    OTHER = "other"


class TransportMode(str, Enum):
    ROAD = "road"
    RAIL = "rail"
    SEA = "sea"
    AIR = "air"


def _name(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not value.strip():
        raise ValueError(f"{label} must be non-empty")
    return value


def _unit(value: object, label: str) -> str:
    return _name(value, label)


def _non_negative_real(value: object, label: str) -> Real:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{label} must be a real number")
    try:
        finite = isfinite(value)
    except OverflowError:
        finite = False
    if not finite or value < 0:
        raise ValueError(f"{label} must be finite and non-negative")
    return value


def _tags(values: Iterable[str], label: str) -> frozenset[str]:
    if isinstance(values, str):
        raise TypeError(f"{label} must be an iterable of strings, not a string")
    try:
        items = tuple(values)
    except TypeError as error:
        raise TypeError(f"{label} must be an iterable of strings") from error
    for item in items:
        _name(item, f"{label} item")
    return frozenset(items)


def _identifier_set(values: Iterable[str], label: str) -> frozenset[str]:
    return _tags(values, label)


def _multiplier_mapping(
    values: Mapping[str, Real], label: str, *, minimum: Real
) -> Mapping[str, Real]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{label} must map link IDs to multipliers")
    copied: dict[str, Real] = {}
    for link_id, value in values.items():
        _name(link_id, "link ID")
        checked = _non_negative_real(value, f"{label} for {link_id!r}")
        if checked < minimum:
            raise ValueError(f"{label} for {link_id!r} must be at least {minimum}")
        copied[link_id] = checked
    return MappingProxyType(copied)


@dataclass(frozen=True)
class Location:
    """A factory, transfer hub, warehouse, destination, or other node."""

    id: str
    kind: LocationKind
    country_code: str | None = None

    def __post_init__(self) -> None:
        _name(self.id, "location ID")
        try:
            kind = self.kind if isinstance(self.kind, LocationKind) else LocationKind(self.kind)
        except (TypeError, ValueError) as error:
            raise ValueError(f"unsupported location kind: {self.kind!r}") from error
        object.__setattr__(self, "kind", kind)
        if self.country_code is not None:
            _name(self.country_code, "country_code")


@dataclass(frozen=True)
class TransportLink:
    """A directed connection with per-traversal and per-quantity attributes.

    ``capacity`` is measured in ``capacity_unit``. Fixed cost is charged once
    per shipment traversal; variable cost and carbon are multiplied by the
    shipment quantity. Transit time is added once per traversal. The network
    validates all units against its declared unit set.
    """

    id: str
    origin_id: str
    destination_id: str
    mode: TransportMode
    capacity: int | None
    capacity_unit: str
    fixed_cost: Real
    variable_cost_per_quantity_unit: Real
    transit_time: Real
    carbon_per_quantity_unit: Real
    available: bool = True
    capabilities: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _name(self.id, "link ID")
        _name(self.origin_id, "link origin ID")
        _name(self.destination_id, "link destination ID")
        if self.origin_id == self.destination_id:
            raise ValueError("a transport link must connect two different locations")
        try:
            mode = self.mode if isinstance(self.mode, TransportMode) else TransportMode(self.mode)
        except (TypeError, ValueError) as error:
            raise ValueError(f"unsupported transport mode: {self.mode!r}") from error
        object.__setattr__(self, "mode", mode)
        if self.capacity is not None:
            if isinstance(self.capacity, bool) or not isinstance(self.capacity, int):
                raise TypeError("link capacity must be a non-negative integer or None")
            if self.capacity < 0:
                raise ValueError("link capacity must be non-negative")
        object.__setattr__(self, "capacity_unit", _unit(self.capacity_unit, "capacity_unit"))
        for attribute in (
            "fixed_cost",
            "variable_cost_per_quantity_unit",
            "transit_time",
            "carbon_per_quantity_unit",
        ):
            object.__setattr__(
                self,
                attribute,
                _non_negative_real(getattr(self, attribute), attribute),
            )
        if not isinstance(self.available, bool):
            raise TypeError("available must be a Boolean")
        object.__setattr__(self, "capabilities", _tags(self.capabilities, "capabilities"))


@dataclass(frozen=True)
class ShipmentRequest:
    """A quantity to move between an origin and destination by a deadline."""

    id: str
    origin_id: str
    destination_id: str
    quantity: int
    quantity_unit: str
    deadline: Real | None = None
    deadline_unit: str | None = None
    required_capabilities: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _name(self.id, "shipment ID")
        _name(self.origin_id, "shipment origin ID")
        _name(self.destination_id, "shipment destination ID")
        if self.origin_id == self.destination_id:
            raise ValueError("shipment origin and destination must differ")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise TypeError("shipment quantity must be a positive integer")
        if self.quantity <= 0:
            raise ValueError("shipment quantity must be positive")
        object.__setattr__(self, "quantity_unit", _unit(self.quantity_unit, "quantity_unit"))
        if self.deadline is not None:
            object.__setattr__(
                self, "deadline", _non_negative_real(self.deadline, "deadline")
            )
            if self.deadline_unit is None:
                raise ValueError("deadline_unit is required when deadline is provided")
            object.__setattr__(self, "deadline_unit", _unit(self.deadline_unit, "deadline_unit"))
        elif self.deadline_unit is not None:
            raise ValueError("deadline_unit requires a deadline")
        object.__setattr__(
            self,
            "required_capabilities",
            _tags(self.required_capabilities, "required_capabilities"),
        )


@dataclass(frozen=True)
class TransportationNetwork:
    """A directed multimodal graph with one explicit unit system."""

    locations: Mapping[str, Location]
    links: tuple[TransportLink, ...]
    quantity_unit: str
    cost_unit: str
    time_unit: str
    carbon_unit: str

    def __post_init__(self) -> None:
        if not isinstance(self.locations, Mapping) or not self.locations:
            raise ValueError("locations must be a non-empty mapping of IDs to Location objects")
        locations: dict[str, Location] = {}
        for location_id, location in self.locations.items():
            _name(location_id, "location mapping key")
            if not isinstance(location, Location):
                raise TypeError("locations must contain Location objects")
            if location_id != location.id:
                raise ValueError(
                    f"location mapping key {location_id!r} does not match ID {location.id!r}"
                )
            locations[location_id] = location
        object.__setattr__(self, "locations", MappingProxyType(locations))

        links = tuple(self.links)
        if any(not isinstance(link, TransportLink) for link in links):
            raise TypeError("links must be a sequence of TransportLink objects")
        link_ids = [link.id for link in links]
        if len(set(link_ids)) != len(link_ids):
            raise ValueError("link IDs must be unique")
        for link in links:
            if link.origin_id not in locations or link.destination_id not in locations:
                raise ValueError(
                    f"link {link.id!r} references an unknown endpoint: "
                    f"{link.origin_id!r} -> {link.destination_id!r}"
                )
        object.__setattr__(self, "links", links)

        for attribute in ("quantity_unit", "cost_unit", "time_unit", "carbon_unit"):
            object.__setattr__(self, attribute, _unit(getattr(self, attribute), attribute))
        for link in links:
            if link.capacity_unit != self.quantity_unit:
                raise ValueError(
                    f"link {link.id!r} capacity unit {link.capacity_unit!r} does not match "
                    f"network quantity unit {self.quantity_unit!r}"
                )

    @property
    def links_by_id(self) -> Mapping[str, TransportLink]:
        """Read-only link lookup keyed by stable link ID."""
        return MappingProxyType({link.id: link for link in self.links})

    def validate_shipment(self, shipment: ShipmentRequest) -> None:
        """Raise a clear error if a shipment is inconsistent with this network."""
        if not isinstance(shipment, ShipmentRequest):
            raise TypeError("shipment must be a ShipmentRequest")
        if shipment.origin_id not in self.locations:
            raise ValueError(f"shipment {shipment.id!r} has unknown origin {shipment.origin_id!r}")
        if shipment.destination_id not in self.locations:
            raise ValueError(
                f"shipment {shipment.id!r} has unknown destination {shipment.destination_id!r}"
            )
        if shipment.quantity_unit != self.quantity_unit:
            raise ValueError(
                f"shipment {shipment.id!r} quantity unit {shipment.quantity_unit!r} does not "
                f"match network unit {self.quantity_unit!r}"
            )
        if shipment.deadline is not None and shipment.deadline_unit != self.time_unit:
            raise ValueError(
                f"shipment {shipment.id!r} deadline unit {shipment.deadline_unit!r} does not "
                f"match network time unit {self.time_unit!r}"
            )


@dataclass(frozen=True)
class DisruptionScenario:
    """Immutable overlay describing link closures and operational changes."""

    id: str
    closed_link_ids: frozenset[str] = frozenset()
    unavailable_location_ids: frozenset[str] = frozenset()
    capacity_overrides: Mapping[str, int] | None = None
    cost_multipliers: Mapping[str, Real] | None = None
    transit_time_multipliers: Mapping[str, Real] | None = None

    def __post_init__(self) -> None:
        _name(self.id, "scenario ID")
        object.__setattr__(
            self, "closed_link_ids", _identifier_set(self.closed_link_ids, "closed_link_ids")
        )
        object.__setattr__(
            self,
            "unavailable_location_ids",
            _identifier_set(self.unavailable_location_ids, "unavailable_location_ids"),
        )

        capacities = {} if self.capacity_overrides is None else self.capacity_overrides
        if not isinstance(capacities, Mapping):
            raise TypeError("capacity_overrides must map link IDs to integer capacities")
        copied_capacities: dict[str, int] = {}
        for link_id, capacity in capacities.items():
            _name(link_id, "link ID")
            if isinstance(capacity, bool) or not isinstance(capacity, int):
                raise TypeError("capacity overrides must be non-negative integers")
            if capacity < 0:
                raise ValueError("capacity overrides must be non-negative")
            copied_capacities[link_id] = capacity
        object.__setattr__(self, "capacity_overrides", MappingProxyType(copied_capacities))
        object.__setattr__(
            self,
            "cost_multipliers",
            _multiplier_mapping(
                {} if self.cost_multipliers is None else self.cost_multipliers,
                "cost multiplier",
                minimum=1,
            ),
        )
        object.__setattr__(
            self,
            "transit_time_multipliers",
            _multiplier_mapping(
                {} if self.transit_time_multipliers is None else self.transit_time_multipliers,
                "transit-time multiplier",
                minimum=1,
            ),
        )

    def validate_for(self, network: TransportationNetwork) -> None:
        """Check that scenario overrides refer to known, reducible resources."""
        if not isinstance(network, TransportationNetwork):
            raise TypeError("network must be a TransportationNetwork")
        link_map = network.links_by_id
        unknown_links = (
            self.closed_link_ids
            | set(self.capacity_overrides)
            | set(self.cost_multipliers)
            | set(self.transit_time_multipliers)
        ) - set(link_map)
        if unknown_links:
            raise ValueError(f"scenario references unknown links: {sorted(unknown_links)!r}")
        unknown_locations = self.unavailable_location_ids - set(network.locations)
        if unknown_locations:
            raise ValueError(
                f"scenario references unknown locations: {sorted(unknown_locations)!r}"
            )
        for link_id, capacity in self.capacity_overrides.items():
            base = link_map[link_id].capacity
            if base is None:
                raise ValueError(
                    f"scenario cannot reduce unbounded link {link_id!r} without a base capacity"
                )
            if capacity > base:
                raise ValueError(
                    f"scenario capacity {capacity} for link {link_id!r} exceeds "
                    f"base capacity {base}"
                )
