import unittest

from qsupply import CVRPProblem


class TestCVRPProblem(unittest.TestCase):
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
        self.valid_routes = {
            "Van A": ("Depot", "C1", "C2", "Depot"),
            "Van B": ("Depot", "C3", "C4", "C5", "Depot"),
        }

    def test_accepts_feasible_routes(self):
        self.assertIsNone(self.problem.validate_routes(self.valid_routes))

    def test_calculates_total_transportation_cost(self):
        self.assertEqual(self.problem.transportation_cost(self.valid_routes), 14)

    def test_rejects_capacity_violation(self):
        routes = {
            "Van A": ("Depot", "C1", "C2", "C3", "Depot"),
            "Van B": ("Depot", "C4", "C5", "Depot"),
        }
        with self.assertRaisesRegex(ValueError, "exceeding capacity"):
            self.problem.validate_routes(routes)

    def test_rejects_duplicate_delivery(self):
        routes = {
            "Van A": ("Depot", "C1", "C2", "Depot"),
            "Van B": ("Depot", "C2", "C3", "C4", "C5", "Depot"),
        }
        with self.assertRaisesRegex(ValueError, "delivered more than once"):
            self.problem.validate_routes(routes)

    def test_rejects_missing_delivery(self):
        routes = {
            "Van A": ("Depot", "C1", "C2", "Depot"),
            "Van B": ("Depot", "C3", "C4", "Depot"),
        }
        with self.assertRaisesRegex(ValueError, "customers are not delivered.*C5"):
            self.problem.validate_routes(routes)

    def test_rejects_invalid_customer_reference(self):
        routes = {
            "Van A": ("Depot", "C1", "C2", "Depot"),
            "Van B": ("Depot", "C3", "Unknown", "C5", "Depot"),
        }
        with self.assertRaisesRegex(ValueError, "invalid customer 'Unknown'"):
            self.problem.validate_routes(routes)

    def test_rejects_malformed_customer_reference(self):
        routes = {
            "Van A": ("Depot", "C1", "C2", "Depot"),
            "Van B": ("Depot", ["C3"], "C4", "C5", "Depot"),
        }
        with self.assertRaisesRegex(ValueError, r"invalid customer \['C3'\]"):
            self.problem.validate_routes(routes)

    def test_rejects_routes_that_do_not_start_and_end_at_depot(self):
        routes = dict(self.valid_routes)
        routes["Van A"] = ("C1", "C2", "Depot")
        with self.assertRaisesRegex(ValueError, "start and end at depot"):
            self.problem.validate_routes(routes)

    def test_rejects_missing_or_unknown_vehicle_routes(self):
        with self.assertRaisesRegex(ValueError, "missing vehicles"):
            self.problem.validate_routes({"Van A": self.valid_routes["Van A"]})
        routes = dict(self.valid_routes)
        routes["Van C"] = ("Depot", "Depot")
        with self.assertRaisesRegex(ValueError, "unknown vehicles"):
            self.problem.validate_routes(routes)


if __name__ == "__main__":
    unittest.main()
