import unittest
from dataclasses import replace

from qsupply.network.global_demo import global_demo_network, global_demo_shipments
from qsupply.network.insights import analyze_route_alternatives
from qsupply.network.planning import ObjectiveReferences, ObjectiveWeights
from qsupply.network.routing import generate_candidate_routes


class TestRouteIntelligence(unittest.TestCase):
    def setUp(self):
        self.profile = global_demo_shipments()[0]
        self.profile = replace(
            self.profile,
            request=replace(self.profile.request, deadline=None, deadline_unit=None),
        )
        self.route = generate_candidate_routes(
            global_demo_network(), self.profile.request, max_routes=1
        )[0]
        self.references = ObjectiveReferences(100, 100, 100, 1)

    def test_pareto_classification_uses_all_four_minimized_metrics(self):
        routes = (
            replace(self.route, id="balanced-a", freight_cost=10, transit_time=10, carbon_kg=10, resilience_exposure=0.2),
            replace(self.route, id="dominated", freight_cost=11, transit_time=11, carbon_kg=11, resilience_exposure=0.3),
            replace(self.route, id="tradeoff", freight_cost=9, transit_time=12, carbon_kg=8, resilience_exposure=0.1),
            replace(self.route, id="balanced-b", freight_cost=10, transit_time=10, carbon_kg=10, resilience_exposure=0.2),
        )
        _, _, analyses = analyze_route_alternatives(
            self.profile,
            routes,
            routes[0],
            ObjectiveWeights(),
            self.references,
        )

        self.assertTrue(analyses["balanced-a"]["pareto_optimal"])
        self.assertFalse(analyses["dominated"]["pareto_optimal"])
        self.assertTrue(analyses["tradeoff"]["pareto_optimal"])
        # Equal points do not strictly dominate one another.
        self.assertTrue(analyses["balanced-b"]["pareto_optimal"])

    def test_zero_baseline_cost_and_carbon_have_unavailable_percentages(self):
        zero_route = replace(
            self.route,
            id="zero-route",
            freight_cost=0,
            transit_time=0,
            carbon_kg=0,
            resilience_exposure=0,
        )
        _, _, analyses = analyze_route_alternatives(
            self.profile,
            (zero_route,),
            zero_route,
            ObjectiveWeights(),
            self.references,
        )

        delta = analyses[zero_route.id]["delta_vs_baseline"]
        self.assertIsNone(delta["cost_savings_percent"])
        self.assertIsNone(delta["carbon_savings_percent"])


if __name__ == "__main__":
    unittest.main()
