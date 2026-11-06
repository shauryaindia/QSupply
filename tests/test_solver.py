import unittest
from fractions import Fraction

from qsupply import (
    IsingModel,
    QUBO,
    ExactQUBOSolver,
    SolverRequest,
    benchmark_solvers,
)
from qsupply.import_export import (
    evaluate_business_objective,
    formulate_import_export_qubo,
    synthetic_import_export_problem,
)
from qsupply.solver import (
    BackendType,
    ExecutionStatus,
    ProblemRepresentation,
)


class TestExactQUBOSolver(unittest.TestCase):
    def setUp(self):
        self.solver = ExactQUBOSolver()

    def test_empty_qubo_and_nonzero_offset(self):
        result = self.solver.solve(
            SolverRequest(QUBO((), {}), constant_offset=Fraction(5, 7))
        )
        self.assertEqual(dict(result.best_binary_assignment), {})
        self.assertEqual(dict(result.best_spin_assignment), {})
        self.assertEqual(result.qubo_energy, 0)
        self.assertEqual(result.full_energy, Fraction(5, 7))
        self.assertEqual(result.ising_energy, Fraction(5, 7))
        self.assertEqual(result.candidate_assignments_evaluated, 1)

    def test_single_variable_negative_rational_coefficient(self):
        qubo = QUBO(("x",), {("x", "x"): Fraction(-3, 2)})
        result = self.solver.solve(SolverRequest(qubo, constant_offset=Fraction(1, 3)))
        self.assertEqual(dict(result.best_binary_assignment), {"x": 1})
        self.assertEqual(dict(result.best_spin_assignment), {"x": -1})
        self.assertEqual(result.solver_reported_energy, Fraction(-3, 2))
        self.assertEqual(result.qubo_energy, Fraction(-3, 2))
        self.assertEqual(result.full_energy, Fraction(-7, 6))
        self.assertEqual(result.ising_energy, result.full_energy)
        self.assertEqual(result.candidate_assignments_evaluated, 2)

    def test_multiple_variables_diagonal_and_off_diagonal(self):
        qubo = QUBO(
            ("x", "y"),
            {("x", "x"): -2, ("y", "y"): -3, ("x", "y"): 4},
        )
        result = self.solver.solve(SolverRequest(qubo, constant_offset=5))
        self.assertEqual(dict(result.best_binary_assignment), {"x": 0, "y": 1})
        self.assertEqual(result.qubo_energy, -3)
        self.assertEqual(result.full_energy, 2)
        self.assertEqual(result.ising_energy, 2)
        self.assertEqual(result.candidate_assignments_evaluated, 4)
        self.assertEqual(result.variable_order, ("x", "y"))

    def test_rational_coefficients_and_large_integer_are_not_float_converted(self):
        qubo = QUBO(
            ("large", "fraction"),
            {
                ("large", "large"): 2**53 + 1,
                ("fraction", "fraction"): Fraction(-5, 4),
                ("large", "fraction"): Fraction(1, 3),
            },
        )
        result = self.solver.solve(SolverRequest(qubo))
        self.assertIsInstance(result.solver_reported_energy, Fraction)
        self.assertIsInstance(result.qubo_energy, Fraction)
        self.assertEqual(result.solver_reported_energy, result.qubo_energy)
        self.assertEqual(result.ising_energy, result.full_energy)

    def test_deterministic_lexicographic_tie_breaking(self):
        qubo = QUBO(("z", "a"), {})
        results = [self.solver.solve(SolverRequest(qubo)) for _ in range(3)]
        for result in results:
            self.assertEqual(dict(result.best_binary_assignment), {"z": 0, "a": 0})
            self.assertEqual(result.candidate_assignments_evaluated, 4)

    def test_maximum_variable_count_is_enforced_before_enumeration(self):
        solver = ExactQUBOSolver(max_variables=2)
        self.assertEqual(solver.max_variables, 2)
        with self.assertRaisesRegex(ValueError, "at most 2 variables"):
            solver.solve(SolverRequest(QUBO(("a", "b", "c"), {})))
        with self.assertRaisesRegex(ValueError, "non-negative"):
            ExactQUBOSolver(max_variables=-1)
        with self.assertRaisesRegex(TypeError, "integer"):
            ExactQUBOSolver(max_variables=True)
        default_limit_problem = QUBO(tuple(f"x{index}" for index in range(21)), {})
        with self.assertRaisesRegex(ValueError, "at most 12 variables"):
            self.solver.solve(SolverRequest(default_limit_problem))

    def test_request_can_select_ising_representation_but_exact_backend_rejects_it(self):
        request = SolverRequest(
            QUBO(("x",), {("x", "x"): 3}),
            constant_offset=7,
            representation=ProblemRepresentation.ISING,
        )
        self.assertIs(request.representation_model, request.ising_model)
        self.assertEqual(request.variable_order, ("x",))
        self.assertEqual(request.ising_model.constant, Fraction(17, 2))
        with self.assertRaisesRegex(ValueError, "does not support ising input"):
            self.solver.solve(request)

    def test_request_rejects_ising_model_with_inconsistent_coefficients(self):
        inconsistent = IsingModel(("x",), 1, {"x": Fraction(-1, 2)}, {})
        with self.assertRaisesRegex(ValueError, "must be equivalent"):
            SolverRequest(QUBO(("x",), {("x", "x"): 1}), ising_model=inconsistent)

    def test_import_export_decoding_validation_and_business_objective(self):
        problem = synthetic_import_export_problem()
        formulation = formulate_import_export_qubo(problem)
        request = SolverRequest(
            qubo=formulation.qubo,
            constant_offset=formulation.offset,
            validator=formulation.check_feasibility,
            decoder=formulation.decode,
            business_objective=lambda selected: evaluate_business_objective(
                problem, selected
            ),
            configuration={"case": "synthetic-import-export"},
            random_seed=11,
        )
        result = self.solver.solve(request)
        self.assertEqual(result.status, ExecutionStatus.COMPLETED)
        self.assertTrue(result.feasible)
        self.assertEqual(dict(result.decoded_solution), {"S1": "B", "S2": "A"})
        self.assertEqual(result.business_objective, 17)
        self.assertEqual(result.qubo_energy, -43)
        self.assertEqual(result.full_energy, 17)
        self.assertEqual(result.ising_energy, 17)
        self.assertEqual(result.candidate_assignments_evaluated, 32)
        self.assertEqual(result.random_seed, 11)
        self.assertEqual(result.configuration["case"], "synthetic-import-export")
        self.assertEqual(
            result.configuration["max_variables"], ExactQUBOSolver.DEFAULT_MAX_VARIABLES
        )

    def test_infeasible_lowest_energy_assignment_is_not_decoded_as_business_solution(self):
        qubo = QUBO(("x",), {("x", "x"): -1})
        decoded = []

        def decode(assignment):
            decoded.append(assignment)
            return {"x": assignment["x"]}

        result = self.solver.solve(
            SolverRequest(qubo, validator=lambda assignment: False, decoder=decode)
        )
        self.assertEqual(dict(result.best_binary_assignment), {"x": 1})
        self.assertFalse(result.feasible)
        self.assertIsNone(result.decoded_solution)
        self.assertIsNone(result.business_objective)
        self.assertEqual(decoded, [])

    def test_validator_failure_is_reported_as_failed_execution(self):
        def fail(_assignment):
            raise RuntimeError("validation unavailable")

        result = self.solver.solve(
            SolverRequest(QUBO(("x",), {}), validator=fail)
        )
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIsNone(result.feasible)
        self.assertIn("validation unavailable", result.error)
        self.assertIsNotNone(result.best_binary_assignment)

    def test_result_is_immutable_and_has_standard_metadata(self):
        result = self.solver.solve(SolverRequest(QUBO(("x",), {})))
        self.assertEqual(result.solver_id, "exact-qubo")
        self.assertEqual(result.backend_type, BackendType.CLASSICAL)
        self.assertEqual(result.representation, ProblemRepresentation.QUBO)
        self.assertTrue(result.run_id)
        with self.assertRaises(TypeError):
            result.best_binary_assignment["x"] = 1
        with self.assertRaises(TypeError):
            result.configuration["max_variables"] = 3


class TestSolverBenchmarking(unittest.TestCase):
    def test_comparison_records_share_problem_size_and_capture_results(self):
        request = SolverRequest(
            QUBO(("a", "b", "c"), {("a", "a"): -1}),
            random_seed=2026,
            configuration={"profile": "test"},
        )
        records = benchmark_solvers(
            request, (ExactQUBOSolver(max_variables=3), ExactQUBOSolver(max_variables=3))
        )
        self.assertEqual(len(records), 2)
        for record in records:
            self.assertEqual(record.problem_size, 3)
            self.assertEqual(record.variable_count, 3)
            self.assertEqual(record.best_energy, -1)
            self.assertEqual(record.candidate_assignments_evaluated, 8)
            self.assertEqual(record.random_seed, 2026)
            self.assertEqual(record.result.status, ExecutionStatus.COMPLETED)
        self.assertNotEqual(records[0].result.run_id, records[1].result.run_id)


if __name__ == "__main__":
    unittest.main()
