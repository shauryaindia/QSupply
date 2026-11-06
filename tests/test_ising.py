import itertools
import unittest
from fractions import Fraction

from qsupply import QUBO, qubo_to_ising, synthetic_import_export_problem
from qsupply.import_export import formulate_import_export_qubo


def assignments(variables):
    for values in itertools.product((0, 1), repeat=len(variables)):
        yield dict(zip(variables, values))


class TestQUBOToIsing(unittest.TestCase):
    def assert_equivalent_for_all_assignments(self, qubo, offset=0):
        ising = qubo_to_ising(qubo, offset=offset)
        self.assertEqual(ising.variables, qubo.variables)
        self.assertEqual(
            dict(ising.variable_indices),
            {variable: index for index, variable in enumerate(qubo.variables)},
        )
        for binary in assignments(qubo.variables):
            with self.subTest(binary=binary):
                self.assertEqual(
                    ising.energy_from_binary(binary),
                    offset + qubo.energy(binary),
                )
                spins = {variable: 1 - 2 * value for variable, value in binary.items()}
                self.assertEqual(ising.energy(spins), offset + qubo.energy(binary))
        return ising

    def test_diagonal_and_sparse_negative_rational_coefficients(self):
        qubo = QUBO(
            ("late", "first", "unused"),
            {
                ("late", "late"): Fraction(-7, 3),
                ("first", "first"): Fraction(5, 2),
                ("late", "first"): Fraction(-11, 5),
                ("unused", "late"): Fraction(2, 7),
            },
        )
        ising = self.assert_equivalent_for_all_assignments(qubo, Fraction(13, 9))
        expected_constant = (
            Fraction(13, 9)
            - Fraction(7, 6)
            + Fraction(5, 4)
            - Fraction(11, 20)
            + Fraction(1, 14)
        )
        self.assertEqual(ising.constant, expected_constant)
        self.assertEqual(ising.quadratic[("late", "first")], Fraction(-11, 20))
        self.assertEqual(ising.quadratic[("late", "unused")], Fraction(1, 14))

    def test_forward_only_reverse_only_and_both_orientations(self):
        cases = (
            {("a", "b"): Fraction(8, 3)},
            {("b", "a"): Fraction(-4, 3)},
            {("a", "b"): Fraction(8, 3), ("b", "a"): Fraction(-4, 3)},
        )
        for coefficients in cases:
            with self.subTest(coefficients=coefficients):
                model = self.assert_equivalent_for_all_assignments(
                    QUBO(("a", "b"), coefficients)
                )
                combined = coefficients.get(("a", "b"), 0) + coefficients.get(
                    ("b", "a"), 0
                )
                self.assertEqual(model.quadratic.get(("a", "b"), 0), combined / 4)

    def test_empty_and_single_variable_models(self):
        empty = self.assert_equivalent_for_all_assignments(QUBO((), {}), Fraction(7, 5))
        self.assertEqual(empty.energy({}), Fraction(7, 5))

        single = QUBO(("x",), {("x", "x"): Fraction(9, 4)})
        ising = self.assert_equivalent_for_all_assignments(single)
        self.assertEqual(ising.linear["x"], Fraction(-9, 8))
        self.assertEqual(ising.constant, Fraction(9, 8))
        self.assertEqual(dict(ising.quadratic), {})

    def test_large_integer_coefficients_keep_exact_ordering(self):
        magnitude = 2**53 + 1
        qubo = QUBO(("x",), {("x", "x"): magnitude})
        ising = qubo_to_ising(qubo)
        self.assertEqual(ising.energy_from_binary({"x": 1}), magnitude)
        self.assertIsInstance(ising.energy_from_binary({"x": 1}), Fraction)

    def test_import_export_offset_preserves_full_penalized_energy(self):
        formulation = formulate_import_export_qubo(synthetic_import_export_problem())
        ising = qubo_to_ising(formulation.qubo, offset=formulation.offset)
        self.assertEqual(ising.variables, formulation.qubo.variables)
        diagonal_constant = sum(
            Fraction(coefficient) / 2
            for (left, right), coefficient in formulation.qubo.coefficients.items()
            if left == right
        )
        pair_constant = sum(
            Fraction(
                formulation.qubo.coefficients.get((left, right), 0)
                + formulation.qubo.coefficients.get((right, left), 0)
            )
            / 4
            for index, left in enumerate(formulation.qubo.variables)
            for right in formulation.qubo.variables[index + 1 :]
        )
        self.assertEqual(
            ising.constant, formulation.offset + diagonal_constant + pair_constant
        )
        for binary in assignments(formulation.qubo.variables):
            self.assertEqual(
                ising.energy_from_binary(binary), formulation.full_energy(binary)
            )

    def test_conversion_does_not_mutate_qubo_and_coefficients_are_read_only(self):
        qubo = QUBO(("b", "a"), {("a", "b"): 6, ("b", "a"): -2})
        original = dict(qubo.coefficients)
        model = qubo_to_ising(qubo)
        self.assertEqual(dict(qubo.coefficients), original)
        with self.assertRaises(TypeError):
            model.linear["a"] = 10
        with self.assertRaises(TypeError):
            model.quadratic[("b", "a")] = 10

    def test_invalid_assignments_are_rejected(self):
        model = qubo_to_ising(QUBO(("x",), {("x", "x"): 1}))
        for assignment in ({}, {"x": 2}, {"x": 1, "extra": 0}):
            with self.subTest(assignment=assignment), self.assertRaises(ValueError):
                model.energy_from_binary(assignment)
        self.assertEqual(
            model.energy_from_binary({"x": True}), model.energy_from_binary({"x": 1})
        )
        for spins in ({}, {"x": 0}, {"x": False}, {"x": 1, "extra": -1}):
            with self.subTest(spins=spins), self.assertRaises(ValueError):
                model.energy(spins)


if __name__ == "__main__":
    unittest.main()
