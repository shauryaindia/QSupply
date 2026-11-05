import unittest
from math import dist

from qsupply import CVRPProblem, NearestNeighborTwoOptSolver


class TestNearestNeighborTwoOptSolver(unittest.TestCase):
    def setUp(self):
        locations = ("Depot", "C1", "C2", "C3", "C4", "C5")
        positions = {location: index for index, location in enumerate(locations)}
        distances = {
            (origin, destination): abs(positions[origin] - positions[destination])
            for origin in locations
            for destination in locations
        }
        self.problem = CVRPProblem(
            depot="Depot",
            customer_demands={"C1": 2, "C2": 3, "C3": 2, "C4": 1, "C5": 2},
            vehicle_capacities={"Van A": 5, "Van B": 5},
            distances=distances,
        )
        self.solver = NearestNeighborTwoOptSolver()

    def test_solution_is_feasible_and_covers_every_customer_once(self):
        result = self.solver.solve(self.problem)
        self.problem.validate_routes(result.routes)
        customers = [
            customer
            for route in result.routes.values()
            for customer in route[1:-1]
        ]
        self.assertCountEqual(customers, self.problem.customer_demands)
        self.assertEqual(len(customers), len(set(customers)))

    def test_solution_respects_vehicle_capacities(self):
        result = self.solver.solve(self.problem)
        for vehicle, route in result.routes.items():
            load = sum(self.problem.customer_demands[c] for c in route[1:-1])
            self.assertLessEqual(load, self.problem.vehicle_capacities[vehicle])

    def test_results_are_deterministic(self):
        first = self.solver.solve(self.problem)
        second = self.solver.solve(self.problem)
        self.assertEqual(dict(first.routes), dict(second.routes))
        self.assertEqual(first.initial_distance, second.initial_distance)
        self.assertEqual(first.total_distance, second.total_distance)

    def test_two_opt_improves_a_nearest_neighbor_route(self):
        coordinates = {
            "Depot": (0, 0),
            "A": (1, 0),
            "B": (4, 0),
            "C": (4, 1),
            "D": (0, 1),
        }
        locations = tuple(coordinates)
        problem = CVRPProblem(
            depot="Depot",
            customer_demands={"A": 1, "B": 1, "C": 1, "D": 1},
            vehicle_capacities={"Van": 4},
            distances={
                (origin, destination): dist(coordinates[origin], coordinates[destination])
                for origin in locations
                for destination in locations
            },
        )

        result = self.solver.solve(problem)
        self.assertLess(result.total_distance, result.initial_distance)
        self.assertAlmostEqual(
            result.total_distance,
            problem.transportation_cost(result.routes),
        )
        self.assertGreater(result.improvement_percent, 0)

    def test_rejects_total_demand_above_total_capacity(self):
        locations = ("Depot", "C1", "C2")
        problem = CVRPProblem(
            depot="Depot",
            customer_demands={"C1": 2, "C2": 2},
            vehicle_capacities={"Van A": 1, "Van B": 2},
            distances={(a, b): 0 if a == b else 1 for a in locations for b in locations},
        )
        with self.assertRaisesRegex(ValueError, "total customer demand.*exceeds total vehicle capacity"):
            self.solver.solve(problem)

    def test_rejects_customer_larger_than_every_vehicle(self):
        locations = ("Depot", "C1")
        problem = CVRPProblem(
            depot="Depot",
            customer_demands={"C1": 5},
            vehicle_capacities={"Van A": 4, "Van B": 3},
            distances={(a, b): 0 if a == b else 1 for a in locations for b in locations},
        )
        with self.assertRaisesRegex(ValueError, "exceeds every vehicle capacity"):
            self.solver.solve(problem)


if __name__ == "__main__":
    unittest.main()
