import unittest
from math import dist
from itertools import permutations

from qsupply import CVRPProblem, ExactCVRPSolver, MAX_EXACT_CUSTOMERS


def make_problem(coordinates, demands, capacities):
    locations = tuple(coordinates)
    distances = {
        (origin, destination): dist(coordinates[origin], coordinates[destination])
        for origin in locations
        for destination in locations
    }
    return CVRPProblem("Depot", demands, capacities, distances)


class TestExactCVRPSolver(unittest.TestCase):
    def setUp(self):
        self.solver = ExactCVRPSolver()

    def test_finds_minimum_single_vehicle_route(self):
        problem = make_problem(
            {
                "Depot": (0, 0),
                "A": (1, 0),
                "B": (4, 0),
                "C": (4, 1),
                "D": (0, 1),
            },
            {"A": 1, "B": 1, "C": 1, "D": 1},
            {"Van": 4},
        )
        solution = self.solver.solve(problem)
        problem.validate_routes(solution.routes)
        self.assertAlmostEqual(solution.total_distance, 10.0)
        self.assertAlmostEqual(solution.total_distance, problem.transportation_cost(solution.routes))

    def test_preserves_integer_precision_above_float_exact_range(self):
        large = 2**53
        locations = ("Depot", "A", "B")
        distances = {(a, b): 0 for a in locations for b in locations}
        distances[("A", "B")] = large
        distances[("B", "A")] = large + 1
        problem = CVRPProblem(
            "Depot", {"A": 1, "B": 1}, {"Van": 2}, distances
        )

        solution = self.solver.solve(problem)

        self.assertEqual(solution.routes["Van"], ("Depot", "A", "B", "Depot"))
        self.assertEqual(solution.total_distance, large)
        self.assertIsInstance(solution.total_distance, int)

    def test_asymmetric_distances_and_zero_demand_match_permutation_brute_force(self):
        locations = ("Depot", "Free", "A", "B")
        distances = {
            (origin, destination): (0 if origin == destination else
                                    (len(origin) * 3 + len(destination) * 5 + ord(destination[0]) % 7))
            for origin in locations
            for destination in locations
        }
        problem = CVRPProblem(
            "Depot", {"Free": 0, "A": 1, "B": 1}, {"Van": 2}, distances
        )
        candidates = (
            problem.transportation_cost({"Van": ("Depot", *order, "Depot")})
            for order in permutations(problem.customer_demands)
        )
        expected = min(candidates)

        solution = self.solver.solve(problem)

        self.assertEqual(solution.total_distance, expected)
        self.assertEqual(set(solution.routes["Van"][1:-1]), set(problem.customer_demands))

    def test_respects_capacities_and_customer_coverage(self):
        problem = make_problem(
            {
                "Depot": (0, 0),
                "A": (1, 0),
                "B": (2, 0),
                "C": (8, 0),
                "D": (9, 0),
            },
            {"A": 2, "B": 2, "C": 2, "D": 2},
            {"Small": 4, "Large": 4},
        )
        solution = self.solver.solve(problem)
        problem.validate_routes(solution.routes)
        visited = [c for route in solution.routes.values() for c in route[1:-1]]
        self.assertCountEqual(visited, problem.customer_demands)
        for vehicle, route in solution.routes.items():
            load = sum(problem.customer_demands[c] for c in route[1:-1])
            self.assertLessEqual(load, problem.vehicle_capacities[vehicle])

    def test_reports_infeasible_capacity_assignment(self):
        problem = make_problem(
            {"Depot": (0, 0), "A": (1, 0), "B": (2, 0)},
            {"A": 3, "B": 3},
            {"Small": 2, "Large": 3},
        )
        with self.assertRaisesRegex(ValueError, "total customer demand.*exceeds total vehicle capacity"):
            self.solver.solve(problem)

    def test_enforces_maximum_supported_customer_count(self):
        coordinates = {"Depot": (0, 0)}
        demands = {}
        for index in range(MAX_EXACT_CUSTOMERS + 1):
            name = f"C{index}"
            coordinates[name] = (index + 1, 0)
            demands[name] = 1
        problem = make_problem(coordinates, demands, {"Van": MAX_EXACT_CUSTOMERS + 1})
        with self.assertRaisesRegex(ValueError, f"at most {MAX_EXACT_CUSTOMERS} customers"):
            self.solver.solve(problem)

    def test_accepts_exactly_the_maximum_supported_customer_count(self):
        coordinates = {"Depot": (0, 0)}
        demands = {}
        for index in range(MAX_EXACT_CUSTOMERS):
            name = f"C{index}"
            coordinates[name] = (index + 1, 0)
            demands[name] = 1
        problem = make_problem(
            coordinates,
            demands,
            {"Van": MAX_EXACT_CUSTOMERS},
        )

        solution = self.solver.solve(problem)

        self.assertEqual(len(solution.routes["Van"]) - 2, MAX_EXACT_CUSTOMERS)


if __name__ == "__main__":
    unittest.main()
