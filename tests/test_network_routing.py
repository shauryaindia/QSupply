import unittest
from dataclasses import replace
from datetime import datetime, timezone

from qsupply.network import (
    DisruptionScenario,
    Location,
    LocationKind,
    ObjectiveWeights,
    ShipmentRequest,
    TransportationNetwork,
    TransportLink,
    TransportMode,
    compare_recovery,
    generate_candidate_routes,
    simulate_movement,
    validate_candidate_route,
)
from qsupply.network.global_demo import (
    global_demo_network,
    global_demo_scenario,
    global_demo_shipments,
)


class TestMultimodalRouteGeneration(unittest.TestCase):
    def test_synthetic_global_network_has_geography_and_expected_regions(self):
        network = global_demo_network()
        self.assertGreaterEqual(len(network.locations), 25)
        self.assertGreaterEqual(len(network.links), 30)
        self.assertTrue(
            all(location.latitude is not None and location.longitude is not None for location in network.locations.values())
        )
        self.assertTrue(all(location.timezone for location in network.locations.values()))
        names = {location.id for location in network.locations.values()}
        self.assertTrue({"shanghai-hub", "mumbai-port", "rotterdam-hub", "new-york-port", "santos-port", "sydney-port"}.issubset(names))
        self.assertEqual({link.mode for link in network.links}, set(TransportMode))
        adjacency = {location_id: set() for location_id in names}
        for link in network.links:
            adjacency[link.origin_id].add(link.destination_id)
        reachable = {"shanghai-hub"}
        pending = ["shanghai-hub"]
        while pending:
            for destination in adjacency[pending.pop()]:
                if destination not in reachable:
                    reachable.add(destination)
                    pending.append(destination)
        self.assertEqual(reachable, names)

    def test_candidate_generation_is_deterministic_and_independently_validated(self):
        network = global_demo_network()
        profile = global_demo_shipments()[0]
        first = generate_candidate_routes(network, profile.request, max_routes=8)
        second = generate_candidate_routes(network, profile.request, max_routes=8)
        self.assertEqual(first, second)
        self.assertGreaterEqual(len(first), 3)
        for route in first:
            validate_candidate_route(network, profile.request, route)
            self.assertEqual(route.location_ids[0], profile.request.origin_id)
            self.assertEqual(route.location_ids[-1], profile.request.destination_id)
            self.assertGreater(route.distance_km, 0)
            self.assertEqual(route.geometry[0], (network.locations[profile.request.origin_id].latitude, network.locations[profile.request.origin_id].longitude))

    def test_independent_validation_rejects_tampered_route_and_leg_metadata(self):
        network = global_demo_network()
        profile = global_demo_shipments()[0]
        route = generate_candidate_routes(network, profile.request)[0]
        with self.assertRaisesRegex(ValueError, "route modes"):
            validate_candidate_route(network, profile.request, replace(route, modes=()))
        tampered_leg = replace(route.legs[0], freight_cost=route.legs[0].freight_cost + 1)
        with self.assertRaisesRegex(ValueError, "route leg freight_cost"):
            validate_candidate_route(
                network,
                profile.request,
                replace(route, legs=(tampered_leg, *route.legs[1:])),
            )

    def test_scenario_capacity_and_closure_remove_invalid_route_candidates(self):
        network = global_demo_network()
        profile = global_demo_shipments()[0]
        scenario = DisruptionScenario(
            "test-suez-closed",
            closed_link_ids={"sea-jebel-rotterdam"},
        )
        routes = generate_candidate_routes(network, profile.request, scenario, max_routes=8)
        self.assertTrue(routes)
        self.assertTrue(all("sea-jebel-rotterdam" not in {leg.link_id for leg in route.legs} for route in routes))
        self.assertTrue(any(TransportMode.AIR in route.modes for route in routes))

    def test_scenario_additive_customs_delay_changes_leg_and_route_time(self):
        network = global_demo_network()
        profile = global_demo_shipments()[0]
        scenario = DisruptionScenario(
            "customs-delay",
            transit_time_additions={"sea-singapore-colombo": 2.5},
        )
        baseline = generate_candidate_routes(network, profile.request, max_routes=20)
        delayed = generate_candidate_routes(network, profile.request, scenario, max_routes=20)
        route_id = next(
            route.id
            for route in baseline
            if "sea-singapore-colombo" in {leg.link_id for leg in route.legs}
        )
        base_route = next(route for route in baseline if route.id == route_id)
        delayed_route = next(route for route in delayed if route.id == route_id)
        self.assertEqual(delayed_route.transit_time, base_route.transit_time + 2.5)
        base_leg = next(leg for leg in base_route.legs if leg.link_id == "sea-singapore-colombo")
        delayed_leg = next(leg for leg in delayed_route.legs if leg.link_id == "sea-singapore-colombo")
        self.assertEqual(delayed_leg.transit_time, base_leg.transit_time + 2.5)
        validate_candidate_route(network, profile.request, delayed_route, scenario)

    def test_route_search_rejects_bad_limits_and_non_geospatial_networks(self):
        network = global_demo_network()
        shipment = global_demo_shipments()[0].request
        with self.assertRaisesRegex(ValueError, "max_routes must be positive"):
            generate_candidate_routes(network, shipment, max_routes=0)

        locations = {
            "a": Location("a", LocationKind.OTHER),
            "b": Location("b", LocationKind.OTHER),
        }
        local_network = TransportationNetwork(
            locations,
            (TransportLink("ab", "a", "b", "road", None, "load", 0, 1, 1, 0),),
            "load", "cost", "day", "carbon",
        )
        local_shipment = ShipmentRequest("local", "a", "b", 1, "load")
        with self.assertRaisesRegex(ValueError, "requires coordinates"):
            generate_candidate_routes(local_network, local_shipment)


class TestMultimodalRecovery(unittest.TestCase):
    def test_weights_must_be_percentages_totaling_one_hundred(self):
        with self.assertRaisesRegex(ValueError, "must total 100"):
            ObjectiveWeights(cost=40, delivery_time=25, carbon=20, resilience=10)
        self.assertEqual(sum(vars(ObjectiveWeights()).values()), 100)

    def test_recovery_respects_shared_capacity_and_keeps_fixed_references(self):
        network = global_demo_network()
        shipments = global_demo_shipments()
        weights = ObjectiveWeights()
        baseline = compare_recovery(network, shipments, None, weights)
        scenario = global_demo_scenario()
        result = compare_recovery(network, shipments, scenario, weights)
        self.assertEqual(result.normalization_references, baseline.normalization_references)
        self.assertTrue(result.recovery_feasible)
        self.assertIsNotNone(result.recovery)
        self.assertEqual(result.baseline.capacity_usage["sea-jebel-rotterdam"], 4)
        self.assertLessEqual(result.recovery.capacity_usage["sea-jebel-rotterdam"], 3)
        self.assertTrue(
            any(
                "sea-jebel-rotterdam" not in {leg.link_id for leg in route.legs}
                for route in result.recovery.routes.values()
            )
        )
        self.assertNotEqual(result.baseline.metrics.total_cost, result.recovery.metrics.total_cost)
        self.assertEqual(result.recovery.method, "exact-enumeration-over-generated-candidates")

    def test_recovery_failure_is_reported_separately_from_resilience_exposure(self):
        network = global_demo_network()
        shipments = global_demo_shipments()
        scenario = DisruptionScenario(
            "synthetic-origin-isolation",
            closed_link_ids={
                "road-shanghai-port",
                "road-shanghai-airport",
                "road-shanghai-rail",
            },
        )
        result = compare_recovery(network, shipments, scenario, ObjectiveWeights())
        self.assertFalse(result.recovery_feasible)
        self.assertIsNone(result.recovery)
        self.assertIn("No capacity-feasible", result.failure_reason)
        self.assertGreaterEqual(result.baseline.metrics.resilience_exposure, 0)

    def test_simulated_position_is_deterministic_and_follows_route_geometry(self):
        network = global_demo_network()
        profile = global_demo_shipments()[0]
        baseline = compare_recovery(network, (profile,), None, ObjectiveWeights())
        route = baseline.baseline.routes[profile.request.id]
        departure = datetime(2026, 1, 1, tzinfo=timezone.utc)
        first = simulate_movement(route, departure, 7, network.time_unit)
        second = simulate_movement(route, departure, 7, network.time_unit)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "in_transit")
        self.assertEqual(first["current_leg_id"], "sea-singapore-colombo")
        position = first["position"]
        self.assertGreaterEqual(position[0], 1.0)
        self.assertLessEqual(position[0], 7.0)
        self.assertGreaterEqual(position[1], 79.0)
        self.assertLessEqual(position[1], 105.0)
        delivered = simulate_movement(route, departure, route.transit_time + 1, network.time_unit)
        self.assertEqual(delivered["status"], "delivered")
        self.assertEqual(delivered["remaining_time"], 0)
