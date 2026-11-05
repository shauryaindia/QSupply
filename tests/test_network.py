import unittest

from qsupply.network import (
    DisruptionScenario,
    Location,
    LocationKind,
    ShipmentRequest,
    TransportationNetwork,
    TransportLink,
    TransportMode,
)


class TestNetworkModels(unittest.TestCase):
    def setUp(self):
        self.locations = {
            "factory": Location("factory", LocationKind.FACTORY, "IN"),
            "port": Location("port", LocationKind.PORT, "IN"),
            "warehouse": Location("warehouse", LocationKind.WAREHOUSE, "NL"),
        }
        self.links = (
            TransportLink(
                "road-1",
                "factory",
                "port",
                TransportMode.ROAD,
                8,
                "load_unit",
                fixed_cost=2,
                variable_cost_per_quantity_unit=3,
                transit_time=1,
                carbon_per_quantity_unit=0.5,
                capabilities={"cold_chain"},
            ),
            TransportLink(
                "sea-1",
                "port",
                "warehouse",
                TransportMode.SEA,
                12,
                "load_unit",
                fixed_cost=5,
                variable_cost_per_quantity_unit=4,
                transit_time=9,
                carbon_per_quantity_unit=1.5,
            ),
        )
        self.network = TransportationNetwork(
            locations=self.locations,
            links=self.links,
            quantity_unit="load_unit",
            cost_unit="EUR",
            time_unit="day",
            carbon_unit="kgCO2e",
        )

    def test_models_a_directed_multimodal_graph_with_declared_units(self):
        self.assertEqual(self.network.links_by_id["road-1"].mode, TransportMode.ROAD)
        self.assertEqual(self.network.links_by_id["sea-1"].capacity_unit, "load_unit")
        self.assertNotIn("port->factory", self.network.links_by_id)
        shipment = ShipmentRequest(
            "shipment-1",
            "factory",
            "warehouse",
            quantity=3,
            quantity_unit="load_unit",
            deadline=14,
            deadline_unit="day",
            required_capabilities={"cold_chain"},
        )
        self.network.validate_shipment(shipment)

    def test_input_mappings_and_tags_are_immutable_copies(self):
        source_locations = dict(self.locations)
        network = TransportationNetwork(
            source_locations,
            self.links,
            "load_unit",
            "EUR",
            "day",
            "kgCO2e",
        )
        source_locations.clear()
        self.assertIn("factory", network.locations)
        with self.assertRaises(TypeError):
            network.locations["new"] = Location("new", LocationKind.OTHER)
        with self.assertRaises(TypeError):
            network.links_by_id["new"] = self.links[0]
        with self.assertRaises(AttributeError):
            self.links[0].capabilities.add("ambient")

    def test_location_validates_id_and_kind(self):
        with self.assertRaisesRegex(ValueError, "location ID must be non-empty"):
            Location(" ", LocationKind.PORT)
        with self.assertRaisesRegex(ValueError, "unsupported location kind"):
            Location("port", "spaceport")
        with self.assertRaisesRegex(TypeError, "location ID must be a string"):
            Location(1, LocationKind.PORT)

    def test_location_validates_geography_timezone_and_transfer_modes(self):
        location = Location(
            "port-geo",
            LocationKind.PORT,
            "IN",
            country_name="India",
            region="South Asia",
            timezone="Asia/Kolkata",
            latitude=18.9,
            longitude=72.8,
            transfer_modes={"road", TransportMode.SEA},
        )
        self.assertEqual(location.latitude, 18.9)
        self.assertEqual(location.transfer_modes, {TransportMode.ROAD, TransportMode.SEA})
        with self.assertRaisesRegex(ValueError, "provided together"):
            Location("one-coordinate", LocationKind.OTHER, latitude=0)
        with self.assertRaisesRegex(ValueError, "latitude"):
            Location("bad-latitude", LocationKind.OTHER, latitude=91, longitude=0)
        with self.assertRaisesRegex(TypeError, "longitude must be a real number"):
            Location("bad-longitude", LocationKind.OTHER, latitude=0, longitude=True)
        with self.assertRaisesRegex(ValueError, "unknown IANA time zone"):
            Location("bad-timezone", LocationKind.OTHER, timezone="Mars/Olympus")

    def test_link_validates_distance_resilience_and_geometry_endpoints(self):
        points = {
            "factory": Location("factory", LocationKind.FACTORY, latitude=1, longitude=2),
            "port": Location("port", LocationKind.PORT, latitude=3, longitude=4),
        }
        link = TransportLink(
            "geo-road",
            "factory",
            "port",
            TransportMode.ROAD,
            5,
            "load_unit",
            1,
            1,
            1,
            0.5,
            distance_km=250,
            geometry=((1, 2), (2, 3), (3, 4)),
            resilience_exposure=0.25,
        )
        TransportationNetwork(points, (link,), "load_unit", "EUR", "day", "kgCO2e")
        mismatched = TransportLink(
            "geo-road-2",
            "factory",
            "port",
            TransportMode.ROAD,
            5,
            "load_unit",
            1,
            1,
            1,
            0.5,
            distance_km=250,
            geometry=((0, 0), (3, 4)),
        )
        with self.assertRaisesRegex(ValueError, "geometry endpoints"):
            TransportationNetwork(points, (mismatched,), "load_unit", "EUR", "day", "kgCO2e")
        with self.assertRaisesRegex(ValueError, "resilience_exposure"):
            TransportLink(
                "risk", "factory", "port", "road", 5, "load_unit", 1, 1, 1, 0.5,
                resilience_exposure=1.1,
            )

    def test_link_accepts_string_mode_and_checks_directed_endpoints(self):
        link = TransportLink(
            "air-1",
            "factory",
            "warehouse",
            "air",
            4,
            "load_unit",
            fixed_cost=0,
            variable_cost_per_quantity_unit=8,
            transit_time=1,
            carbon_per_quantity_unit=5,
        )
        self.assertIs(link.mode, TransportMode.AIR)
        with self.assertRaisesRegex(ValueError, "unknown endpoint"):
            TransportationNetwork(
                self.locations,
                (TransportLink(
                    "bad", "factory", "missing", "road", 1, "load_unit", 0, 1, 1, 1
                ),),
                "load_unit", "EUR", "day", "kgCO2e",
            )

    def test_network_rejects_duplicate_links_and_location_key_mismatch(self):
        with self.assertRaisesRegex(ValueError, "link IDs must be unique"):
            TransportationNetwork(
                self.locations,
                (self.links[0], self.links[0]),
                "load_unit", "EUR", "day", "kgCO2e",
            )
        with self.assertRaisesRegex(ValueError, "does not match ID"):
            TransportationNetwork(
                {"wrong": self.locations["factory"]},
                (),
                "load_unit", "EUR", "day", "kgCO2e",
            )

    def test_network_requires_all_link_capacities_to_use_declared_quantity_unit(self):
        wrong_units = (TransportLink(
            "bad-unit", "factory", "port", "road", 5, "kg", 0, 1, 1, 1
        ),)
        with self.assertRaisesRegex(ValueError, "does not match network quantity unit"):
            TransportationNetwork(
                self.locations, wrong_units, "load_unit", "EUR", "day", "kgCO2e"
            )

    def test_link_rejects_bad_capacity_and_non_finite_costs(self):
        for capacity in (-1, 1.5, True):
            with self.subTest(capacity=capacity):
                with self.assertRaises((TypeError, ValueError)):
                    TransportLink(
                        "bad", "factory", "port", "road", capacity,
                        "load_unit", 0, 1, 1, 1,
                    )
        for value in (-1, float("inf"), float("nan"), True):
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    TransportLink(
                        "bad", "factory", "port", "road", 1,
                        "load_unit", 0, value, 1, 1,
                    )

    def test_link_rejects_unknown_modes_self_loops_and_invalid_availability(self):
        with self.assertRaisesRegex(ValueError, "unsupported transport mode"):
            TransportLink("x", "a", "b", "teleport", 1, "unit", 0, 0, 0, 0)
        with self.assertRaisesRegex(ValueError, "different locations"):
            TransportLink("x", "a", "a", "road", 1, "unit", 0, 0, 0, 0)
        with self.assertRaisesRegex(TypeError, "available must be a Boolean"):
            TransportLink("x", "a", "b", "road", 1, "unit", 0, 0, 0, 0, available=1)

    def test_shipment_requires_positive_integer_quantity_and_explicit_units(self):
        for quantity in (0, -1):
            with self.subTest(quantity=quantity):
                with self.assertRaisesRegex(ValueError, "quantity must be positive"):
                    ShipmentRequest("s", "factory", "warehouse", quantity, "load_unit")
        for quantity in (1.2, True):
            with self.subTest(quantity=quantity):
                with self.assertRaisesRegex(TypeError, "positive integer"):
                    ShipmentRequest("s", "factory", "warehouse", quantity, "load_unit")
        with self.assertRaisesRegex(ValueError, "deadline_unit is required"):
            ShipmentRequest("s", "factory", "warehouse", 1, "load_unit", 3)

    def test_network_checks_shipment_endpoints_and_units(self):
        with self.assertRaisesRegex(ValueError, "unknown origin"):
            self.network.validate_shipment(
                ShipmentRequest("s", "missing", "warehouse", 1, "load_unit")
            )
        with self.assertRaisesRegex(ValueError, "quantity unit"):
            self.network.validate_shipment(
                ShipmentRequest("s", "factory", "warehouse", 1, "pallet")
            )
        with self.assertRaisesRegex(ValueError, "deadline unit"):
            self.network.validate_shipment(
                ShipmentRequest("s", "factory", "warehouse", 1, "load_unit", 2, "hour")
            )

    def test_shipment_rejects_same_origin_and_destination(self):
        with self.assertRaisesRegex(ValueError, "origin and destination must differ"):
            ShipmentRequest("s", "factory", "factory", 1, "load_unit")

    def test_disruption_scenario_validates_known_links_locations_and_reductions(self):
        scenario = DisruptionScenario(
            "corridor-closed",
            closed_link_ids={"sea-1"},
            unavailable_location_ids={"port"},
            capacity_overrides={"road-1": 4},
            cost_multipliers={"road-1": 1.5},
            transit_time_multipliers={"sea-1": 2},
        )
        scenario.validate_for(self.network)
        self.assertEqual(scenario.capacity_overrides["road-1"], 4)
        with self.assertRaisesRegex(ValueError, "unknown links"):
            DisruptionScenario("bad", closed_link_ids={"missing"}).validate_for(self.network)
        with self.assertRaisesRegex(ValueError, "unknown locations"):
            DisruptionScenario(
                "bad", unavailable_location_ids={"missing"}
            ).validate_for(self.network)
        with self.assertRaisesRegex(ValueError, "exceeds base capacity"):
            DisruptionScenario("bad", capacity_overrides={"road-1": 9}).validate_for(self.network)

    def test_disruption_scenario_rejects_invalid_overrides_and_multipliers(self):
        for value in (-1, 1.5, True):
            with self.subTest(capacity=value):
                with self.assertRaises((TypeError, ValueError)):
                    DisruptionScenario("bad", capacity_overrides={"road-1": value})
        for value in (0.5, float("inf"), float("nan")):
            with self.subTest(multiplier=value):
                with self.assertRaises(ValueError):
                    DisruptionScenario("bad", cost_multipliers={"road-1": value})
        with self.assertRaisesRegex(ValueError, "unbounded link"):
            unbounded = TransportLink(
                "unbounded", "factory", "warehouse", "road", None,
                "load_unit", 0, 1, 1, 1,
            )
            network = TransportationNetwork(
                self.locations, (unbounded,), "load_unit", "EUR", "day", "kgCO2e"
            )
            DisruptionScenario("bad", capacity_overrides={"unbounded": 1}).validate_for(network)


if __name__ == "__main__":
    unittest.main()
