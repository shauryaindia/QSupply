import unittest

from qsupply import (
    CVRPProblem,
    benchmark_cvrp,
    benchmark_suite,
    generate_synthetic_cvrp,
    synthetic_benchmark_suite,
)


class TestCVRPBenchmarking(unittest.TestCase):
    def test_benchmark_includes_all_methods_and_correct_gaps(self):
        problem = generate_synthetic_cvrp(5, seed=17)
        report = benchmark_cvrp(problem, "test-five")
        self.assertEqual(report.instance_name, "test-five")
        self.assertEqual(report.customer_count, 5)
        self.assertEqual(
            [result.method for result in report.results],
            ["nearest-neighbour", "nearest-neighbour+2-opt", "exact"],
        )
        exact = report.result_for("exact")
        self.assertEqual(exact.optimality_gap_percent, 0.0)
        self.assertTrue(all(result.feasible for result in report.results))
        for result in report.results:
            self.assertGreaterEqual(result.vehicles_used, 1)
            expected_gap = 100 * (result.total_distance - exact.total_distance) / exact.total_distance
            self.assertAlmostEqual(result.optimality_gap_percent, expected_gap)

    def test_records_greedy_failure_and_continues_to_exact_solution(self):
        locations = ("Depot", "A", "B", "C")
        distances = {
            (origin, destination): 0 if origin == destination else 1
            for origin in locations
            for destination in locations
        }
        problem = CVRPProblem(
            "Depot", {"A": 4, "B": 3, "C": 3}, {"V6": 6, "V4": 4}, distances
        )

        report = benchmark_cvrp(problem, "greedy-blocked")

        self.assertEqual(report.result_for("nearest-neighbour").status, "construction_failed")
        self.assertIsNone(report.result_for("nearest-neighbour").feasible)
        self.assertIsNone(report.result_for("nearest-neighbour").total_distance)
        self.assertIsNone(report.result_for("nearest-neighbour").optimality_gap_percent)
        self.assertEqual(report.result_for("nearest-neighbour+2-opt").status, "construction_failed")
        exact = report.result_for("exact")
        self.assertEqual(exact.status, "success")
        self.assertTrue(exact.feasible)
        self.assertEqual(exact.total_distance, 5)

    def test_benchmark_gap_preserves_large_integer_route_costs(self):
        large = 2**53
        locations = ("Depot", "A", "B")
        distances = {(a, b): 0 for a in locations for b in locations}
        distances[("A", "B")] = large
        distances[("B", "A")] = large + 1
        problem = CVRPProblem("Depot", {"A": 1, "B": 1}, {"Van": 2}, distances)

        report = benchmark_cvrp(problem, "large-integers")

        exact = report.result_for("exact")
        self.assertEqual(exact.routes["Van"], ("Depot", "A", "B", "Depot"))
        self.assertEqual(exact.total_distance, large)
        self.assertEqual(report.result_for("nearest-neighbour").total_distance, large)
        self.assertEqual(report.result_for("nearest-neighbour").optimality_gap_percent, 0.0)

    def test_detects_capacity_partition_infeasibility(self):
        locations = ("Depot", "A", "B", "C")
        distances = {
            (origin, destination): 0 if origin == destination else 1
            for origin in locations
            for destination in locations
        }
        problem = CVRPProblem(
            "Depot", {"A": 4, "B": 4, "C": 2}, {"V1": 5, "V2": 5}, distances
        )

        report = benchmark_cvrp(problem, "bin-packing-infeasible")

        exact = report.result_for("exact")
        self.assertEqual(exact.status, "problem_infeasible")
        self.assertFalse(exact.feasible)
        self.assertIsNone(exact.total_distance)

    def test_marks_proven_infeasibility_separately_from_heuristic_failure(self):
        locations = ("Depot", "A")
        distances = {
            (origin, destination): 0 if origin == destination else 1
            for origin in locations
            for destination in locations
        }
        problem = CVRPProblem("Depot", {"A": 5}, {"Van": 4}, distances)

        report = benchmark_cvrp(problem, "impossible")

        self.assertEqual(report.result_for("nearest-neighbour").status, "construction_failed")
        self.assertIsNone(report.result_for("nearest-neighbour").feasible)
        self.assertEqual(report.result_for("exact").status, "problem_infeasible")
        self.assertFalse(report.result_for("exact").feasible)

    def test_records_seed_and_complete_instance_configuration(self):
        report = benchmark_suite(seed=2026)[0]
        self.assertEqual(report.instance_seed, 2031)
        configuration = report.instance_configuration
        self.assertEqual(configuration["depot"], "Depot")
        self.assertEqual(len(configuration["customer_demands"]), 5)
        self.assertTrue(configuration["vehicle_capacities"])
        self.assertTrue(configuration["distances"])

    def test_synthetic_data_reproduces_for_a_seed(self):
        first = generate_synthetic_cvrp(7, seed=42)
        second = generate_synthetic_cvrp(7, seed=42)
        self.assertEqual(dict(first.customer_demands), dict(second.customer_demands))
        self.assertEqual(dict(first.vehicle_capacities), dict(second.vehicle_capacities))
        self.assertEqual(dict(first.distances), dict(second.distances))

    def test_suite_contains_5_7_and_9_customer_instances(self):
        suite = synthetic_benchmark_suite(seed=9)
        self.assertEqual([len(problem.customer_demands) for problem in suite.values()], [5, 7, 9])

    def test_gap_is_undefined_when_exact_distance_is_zero(self):
        locations = ("Depot", "Customer")
        problem = CVRPProblem(
            "Depot",
            {"Customer": 1},
            {"Vehicle": 1},
            {(origin, destination): 0 for origin in locations for destination in locations},
        )
        report = benchmark_cvrp(problem)
        self.assertTrue(all(result.optimality_gap_percent is None for result in report.results))

    def test_benchmark_suite_reproduces_solutions(self):
        first = benchmark_suite(seed=2026)
        second = benchmark_suite(seed=2026)
        self.assertEqual([r.instance_name for r in first], [r.instance_name for r in second])
        for first_report, second_report in zip(first, second):
            self.assertEqual(first_report.customer_count, second_report.customer_count)
            for first_result, second_result in zip(first_report.results, second_report.results):
                self.assertEqual(first_result.routes, second_result.routes)
                self.assertEqual(first_result.total_distance, second_result.total_distance)


if __name__ == "__main__":
    unittest.main()
