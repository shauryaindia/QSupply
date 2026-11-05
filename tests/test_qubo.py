import unittest
from math import inf, nan

from qsupply import QUBO


class TestQUBO(unittest.TestCase):
    def setUp(self):
        # E(x) = -2*x0 - 3*x1 + 4*x0*x1
        self.qubo = QUBO(
            variables=("x0", "x1"),
            coefficients={
                ("x0", "x0"): -2,
                ("x1", "x1"): -3,
                ("x0", "x1"): 4,
            },
        )

    def test_known_assignment_energy(self):
        self.assertEqual(self.qubo.energy({"x0": 1, "x1": 1}), -1)

    def test_multiple_assignments(self):
        self.assertEqual(self.qubo.energy({"x0": 0, "x1": 0}), 0)
        self.assertEqual(self.qubo.energy({"x0": 1, "x1": 0}), -2)
        self.assertEqual(self.qubo.energy({"x0": 0, "x1": 1}), -3)
        self.assertEqual(self.qubo.energy({"x0": 1, "x1": 1}), -1)

    def test_rejects_non_binary_values(self):
        for value in (-1, 2, 0.5, "1", None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "must be 0 or 1"):
                    self.qubo.energy({"x0": value, "x1": 0})

    def test_rejects_missing_variable(self):
        with self.assertRaisesRegex(ValueError, "missing variables.*x1"):
            self.qubo.energy({"x0": 1})

    def test_rejects_unknown_variable(self):
        with self.assertRaisesRegex(ValueError, "unknown variables.*x2"):
            self.qubo.energy({"x0": 1, "x1": 0, "x2": 1})

    def test_rejects_non_mapping_assignment(self):
        with self.assertRaisesRegex(TypeError, "assignment must be a mapping"):
            self.qubo.energy([1, 0])

    def test_rejects_coefficient_for_undeclared_variable(self):
        with self.assertRaisesRegex(ValueError, "declared variables"):
            QUBO(("x0",), {("x0", "x1"): 1})

    def test_diagonal_coefficients_are_linear_for_binary_values(self):
        model = QUBO(("x0",), {("x0", "x0"): 7})
        self.assertEqual(model.energy({"x0": 0}), 0)
        self.assertEqual(model.energy({"x0": 1}), 7)

    def test_ordered_off_diagonal_terms_are_not_symmetrized(self):
        forward = QUBO(("x0", "x1"), {("x0", "x1"): 4})
        reverse = QUBO(("x0", "x1"), {("x1", "x0"): 4})
        both = QUBO(("x0", "x1"), {("x0", "x1"): 4, ("x1", "x0"): 4})
        assignment = {"x0": 1, "x1": 1}
        self.assertEqual(forward.energy(assignment), 4)
        self.assertEqual(reverse.energy(assignment), 4)
        self.assertEqual(both.energy(assignment), 8)

    def test_coefficients_are_immutable(self):
        model = QUBO(("x0",), {("x0", "x0"): 2})
        with self.assertRaises(TypeError):
            model.coefficients[("x0", "x0")] = 5

    def test_rejects_duplicate_variables(self):
        with self.assertRaisesRegex(ValueError, "variables must be unique"):
            QUBO(("x0", "x0"), {})

    def test_rejects_string_as_variables_collection(self):
        with self.assertRaisesRegex(TypeError, "not a string"):
            QUBO("x0", {})

    def test_rejects_malformed_coefficient_pairs(self):
        for pair in ("x0", ("x0",), ("x0", 1)):
            with self.subTest(pair=pair):
                with self.assertRaisesRegex(ValueError, "pair of declared variables"):
                    QUBO(("x0",), {pair: 1})

    def test_rejects_invalid_and_non_finite_coefficients(self):
        for weight in (True, "2", None):
            with self.subTest(weight=weight):
                with self.assertRaisesRegex(TypeError, "must be a real number"):
                    QUBO(("x0",), {("x0", "x0"): weight})
        for weight in (nan, inf, -inf, 10**1000):
            with self.subTest(weight=repr(weight)[:20]):
                with self.assertRaisesRegex(ValueError, "must be finite"):
                    QUBO(("x0",), {("x0", "x0"): weight})

    def test_accepts_boolean_assignments_as_binary_values(self):
        self.assertEqual(self.qubo.energy({"x0": True, "x1": False}), -2)


if __name__ == "__main__":
    unittest.main()
