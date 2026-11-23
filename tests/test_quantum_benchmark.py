import unittest
from fractions import Fraction

from qsupply import QUBO, SolverRequest
from qsupply.quantum_benchmark import (
    _objective_statistics,
    benchmark_qaoa_backends,
    benchmark_qaoa_backends_repeated,
)
from qsupply.solver import (
    BackendType,
    ExecutionStatus,
    ProblemRepresentation,
    SolverMetadata,
    SolverResult,
)


class _RecordedQAOA:
    @property
    def metadata(self):
        return SolverMetadata(
            "test-qaoa", "Test QAOA", "1", BackendType.SIMULATOR,
            frozenset({ProblemRepresentation.ISING}),
        )

    def solve(self, request):
        assignment = {"a": 1, "b": 0}
        energy = request.qubo.energy(assignment)
        full = request.constant_offset + energy
        feasible = request.validator(assignment) if request.validator else None
        return SolverResult(
            run_id="benchmark-run", solver_id="test-qaoa", solver_name="Test QAOA",
            solver_version="1", backend_type=BackendType.SIMULATOR,
            representation=ProblemRepresentation.ISING, variable_order=request.variable_order,
            best_binary_assignment=assignment,
            best_spin_assignment={"a": -1, "b": 1}, solver_reported_energy=full,
            qubo_energy=energy, full_energy=full, ising_energy=full,
            decoded_solution=None, business_objective=None, feasible=feasible,
            feasibility_details=(), candidate_assignments_evaluated=64,
            execution_time_seconds=0.01,
            configuration={"depth": 2, "shots_per_evaluation": 32}, random_seed=8,
            status=ExecutionStatus.COMPLETED, backend_name="Test state-vector simulator",
            backend_version="2", sample_count=64, sample_frequencies={(1, 0): 8},
            feasible_sample_rate=0.75, optimizer_iterations=3, circuit_depth=8,
            optimization_time_seconds=0.003, circuit_execution_time_seconds=0.007,
        )


class _OneVariableQAOA:
    def __init__(self, assignment_for_seed, *, with_metadata=False):
        self.assignment_for_seed = assignment_for_seed
        self.with_metadata = with_metadata
        self.seen_seeds = []

    @property
    def metadata(self):
        return SolverMetadata(
            "one-variable-qaoa", "One Variable QAOA", "1", BackendType.SIMULATOR,
            frozenset({ProblemRepresentation.ISING}),
        )

    def solve(self, request):
        from qsupply.execution import ExecutionMetadata, ExecutionMode

        seed = request.random_seed
        self.seen_seeds.append(seed)
        assignment = {"x": self.assignment_for_seed(seed)}
        energy = request.qubo.energy(assignment)
        full = request.constant_offset + energy
        feasible = request.validator(assignment) if request.validator else None
        decoded = request.decoder(assignment) if feasible and request.decoder else None
        business = request.business_objective(decoded) if decoded is not None and request.business_objective else None
        metadata = (
            ExecutionMetadata(
                "one-variable-qaoa", "One Variable QAOA", "1",
                ExecutionMode.LOCAL_SIMULATOR, "whole solver call",
            )
            if self.with_metadata else None
        )
        return SolverResult(
            run_id=f"run-{seed}", solver_id="one-variable-qaoa", solver_name="One Variable QAOA",
            solver_version="1", backend_type=BackendType.SIMULATOR,
            representation=ProblemRepresentation.ISING, variable_order=("x",),
            best_binary_assignment=assignment,
            best_spin_assignment={"x": 1 - 2 * assignment["x"]},
            solver_reported_energy=full, qubo_energy=energy, full_energy=full,
            ising_energy=full, decoded_solution=decoded, business_objective=business,
            feasible=feasible, feasibility_details=(), candidate_assignments_evaluated=0,
            execution_time_seconds=float(seed or 1) / 100,
            configuration={"depth": 1, "shots_per_evaluation": 20}, random_seed=seed,
            status=ExecutionStatus.COMPLETED, backend_name="One Variable QAOA",
            backend_version="1", feasible_sample_rate=0.5,
            execution_metadata=metadata,
        )

class TestQuantumBenchmark(unittest.TestCase):
    def test_rational_objective_statistics_retain_exact_moments(self):
        stats = _objective_statistics("exact", [2**60, 2**60 + 2])
        self.assertEqual(stats.mean_exact, Fraction(2**60 + 1))
        self.assertEqual(stats.median_exact, Fraction(2**60 + 1))
        self.assertEqual(stats.variance_exact, Fraction(1))
        self.assertEqual(stats.standard_deviation_exact, Fraction(1))
        self.assertEqual(stats.best, 2**60)
        self.assertEqual(stats.worst, 2**60 + 2)
        self.assertEqual(stats.mean, float(2**60 + 1))

    def test_fraction_statistics_and_irrational_standard_deviation(self):
        stats = _objective_statistics("fraction", [Fraction(1, 3), Fraction(2, 3)])
        self.assertEqual(stats.mean_exact, Fraction(1, 2))
        self.assertEqual(stats.median_exact, Fraction(1, 2))
        self.assertEqual(stats.variance_exact, Fraction(1, 36))
        self.assertEqual(stats.standard_deviation_exact, Fraction(1, 6))
        irrational = _objective_statistics("irrational", [0, 1])
        self.assertEqual(irrational.variance_exact, Fraction(1, 4))
        self.assertEqual(irrational.standard_deviation_exact, Fraction(1, 2))
        irrational = _objective_statistics("irrational", [0, 1, 1])
        self.assertEqual(irrational.variance_exact, Fraction(2, 9))
        self.assertIsNone(irrational.standard_deviation_exact)

    def test_exact_statistics_survive_values_outside_legacy_float_range(self):
        value = 10**1000
        stats = _objective_statistics("large", [value, value + 2])
        self.assertEqual(stats.mean_exact, Fraction(value + 1))
        self.assertEqual(stats.variance_exact, Fraction(1))
        self.assertIsNone(stats.mean)
        self.assertIsNone(stats.standard_deviation)

    def test_exact_and_qaoa_records_share_full_energy_reference(self):
        qubo = QUBO(("a", "b"), {("a", "a"): -2, ("b", "b"): 1})
        request = SolverRequest(
            qubo,
            constant_offset=Fraction(5, 3),
            validator=lambda assignment: assignment["a"] == 1,
            random_seed=8,
        )
        exact_energy = Fraction(-1, 3)
        # The exact candidate is feasible and its offset is preserved for both
        # methods. The second adapter's gap is independently computed.
        records = benchmark_qaoa_backends("two-variable", request, [_RecordedQAOA()])
        self.assertEqual([record.solver_id for record in records], ["exact-qubo", "test-qaoa"])
        self.assertEqual(records[0].exact_optimum, exact_energy)
        self.assertEqual(records[0].best_sampled_energy, exact_energy)
        self.assertEqual(records[0].absolute_energy_gap, 0)
        self.assertEqual(records[0].penalized_minimum_feasibility, "feasible")
        self.assertEqual(records[0].best_feasible_full_energy, exact_energy)
        self.assertIsNotNone(records[0].feasible_reference_enumeration_time_seconds)
        self.assertEqual(
            records[1].feasible_reference_enumeration_time_seconds,
            records[0].feasible_reference_enumeration_time_seconds,
        )
        self.assertEqual(records[1].exact_optimum, exact_energy)
        self.assertEqual(records[1].best_sampled_energy, exact_energy)
        self.assertEqual(records[1].absolute_energy_gap, 0)
        self.assertEqual(records[1].relative_energy_gap_percent, 0.0)
        self.assertEqual(records[1].feasible_sample_fraction, 0.75)
        self.assertTrue(records[1].best_sample_feasible)
        self.assertEqual(records[1].qaoa_depth, 2)
        self.assertEqual(records[1].shots, 32)
        self.assertEqual(records[1].execution_mode, "local simulator execution")
        self.assertEqual(records[1].backend_type, BackendType.SIMULATOR)
        self.assertEqual(records[1].optimization_time_seconds, 0.003)
        self.assertEqual(records[1].circuit_execution_time_seconds, 0.007)

    def test_relative_gap_is_unavailable_when_exact_energy_is_zero(self):
        request = SolverRequest(QUBO(("a", "b"), {}))

        class ZeroEnergyQAOA(_RecordedQAOA):
            def solve(self, request):
                result = super().solve(request)
                from dataclasses import replace

                return replace(result, full_energy=Fraction(1, 4), qubo_energy=Fraction(1, 4), ising_energy=Fraction(1, 4))

        records = benchmark_qaoa_backends("zero-optimum", request, [ZeroEnergyQAOA()])
        self.assertEqual(records[1].absolute_energy_gap, Fraction(1, 4))
        self.assertIsNone(records[1].relative_energy_gap_percent)

    def test_rejects_ising_source_and_bad_identifier(self):
        request = SolverRequest(QUBO(("x",), {}))
        with self.assertRaisesRegex(ValueError, "problem_id"):
            benchmark_qaoa_backends(" ", request, [])
        ising_request = SolverRequest(QUBO(("x",), {}), representation=ProblemRepresentation.ISING)
        with self.assertRaisesRegex(ValueError, "QUBO representation"):
            benchmark_qaoa_backends("case", ising_request, [])

    def test_infeasible_penalized_minimum_is_not_reported_as_feasible_optimum(self):
        request = SolverRequest(
            QUBO(("x",), {("x", "x"): -5}),
            validator=lambda assignment: assignment["x"] == 0,
            decoder=lambda assignment: dict(assignment),
            business_objective=lambda _decoded: 10,
        )
        solver = _OneVariableQAOA(lambda _seed: 0)
        exact, sampled = benchmark_qaoa_backends("infeasible-min", request, [solver])
        self.assertEqual(exact.penalized_model_minimum, -5)
        self.assertEqual(exact.exact_optimum, -5)  # backwards-compatible alias
        self.assertEqual(exact.penalized_minimum_feasibility, "infeasible")
        self.assertEqual(exact.best_feasible_business_objective, 10)
        self.assertEqual(exact.best_feasible_full_energy, 0)
        self.assertEqual(dict(exact.best_feasible_full_energy_assignment), {"x": 0})
        self.assertEqual(dict(exact.best_feasible_business_assignment), {"x": 0})
        self.assertEqual(sampled.penalized_minimum_feasibility, "infeasible")
        self.assertEqual(sampled.feasibility_status, "feasible")
        self.assertEqual(sampled.gap_reference, "penalized_qubo_minimum")

    def test_no_feasible_assignment_is_reported_as_unavailable_reference(self):
        request = SolverRequest(QUBO(("x",), {}), validator=lambda _assignment: False)
        exact, sampled = benchmark_qaoa_backends(
            "no-feasible", request, [_OneVariableQAOA(lambda _seed: 0)]
        )
        self.assertEqual(exact.penalized_minimum_feasibility, "infeasible")
        self.assertIsNone(exact.best_feasible_full_energy)
        self.assertIsNone(sampled.best_feasible_full_energy)

    def test_feasible_business_reference_is_separate_from_feasible_qubo_minimum(self):
        request = SolverRequest(
            QUBO(("x",), {("x", "x"): -2}),
            validator=lambda _assignment: True,
            decoder=lambda assignment: dict(assignment),
            business_objective=lambda decoded: decoded["x"],
        )
        exact, _sampled = benchmark_qaoa_backends(
            "different-objectives", request, [_OneVariableQAOA(lambda _seed: 1)]
        )
        self.assertEqual(exact.penalized_model_minimum, -2)
        self.assertEqual(exact.penalized_minimum_feasibility, "feasible")
        self.assertEqual(exact.business_objective, 1)
        self.assertEqual(exact.best_feasible_full_energy, -2)
        self.assertEqual(exact.best_feasible_business_objective, 0)
        self.assertEqual(dict(exact.best_feasible_full_energy_assignment), {"x": 1})
        self.assertEqual(dict(exact.best_feasible_business_assignment), {"x": 0})

    def test_repeated_runs_report_explicit_seed_statistics_and_timing_scopes(self):
        request = SolverRequest(
            QUBO(("x",), {}),
            validator=lambda _assignment: True,
            decoder=lambda assignment: dict(assignment),
            business_objective=lambda decoded: decoded["x"],
        )
        solver = _OneVariableQAOA(lambda seed: 0 if seed in (11, 33) else 1)
        report = benchmark_qaoa_backends_repeated(
            "seeded", request, [solver], seeds=(11, 22, 33)
        )
        summary = report.summaries[0]
        stats = summary.objective_statistics
        self.assertEqual(solver.seen_seeds, [11, 22, 33])
        self.assertEqual([run.requested_seed for run in report.runs], [11, 22, 33])
        self.assertEqual(stats.metric, "business_objective (feasible runs only)")
        self.assertEqual((stats.best, stats.worst), (0, 1))
        self.assertAlmostEqual(stats.mean, 1 / 3)
        self.assertEqual(stats.median, 0)
        self.assertAlmostEqual(stats.standard_deviation, (2 / 9) ** 0.5)
        self.assertEqual(summary.feasibility_rate, 1.0)
        self.assertAlmostEqual(summary.optimal_feasible_success_probability, 2 / 3)
        self.assertEqual(summary.mean_feasible_sample_fraction, 0.5)
        for actual, expected in zip(summary.per_run_execution_times_seconds, (0.11, 0.22, 0.33)):
            self.assertAlmostEqual(actual, expected)
        self.assertAlmostEqual(summary.aggregate_execution_time_seconds, 0.66)
        self.assertEqual(summary.feasibility_evaluated_run_count, 3)
        self.assertEqual(summary.seeded_run_count, 3)
        self.assertEqual(summary.full_energy_statistics.count, 3)
        self.assertEqual(summary.business_objective_statistics.count, 3)
        self.assertEqual(report.runs[0].decoded_solution, {"x": 0})
        self.assertIn("aggregate is the sum", summary.timing_scope)
        self.assertEqual(report.exact_reference.feasibility_status, "feasible")

    def test_missing_execution_metadata_stays_unavailable(self):
        request = SolverRequest(QUBO(("x",), {}), validator=lambda _assignment: True)
        report = benchmark_qaoa_backends_repeated(
            "metadata-absent", request,
            [_OneVariableQAOA(lambda _seed: 0)], seeds=(4, 5),
        )
        self.assertTrue(all(run.execution_metadata is None for run in report.runs))
        self.assertTrue(all(run.execution_mode_detail is None for run in report.runs))
        self.assertTrue(all(run.execution_mode_source == "legacy_backend_type_category" for run in report.runs))
        self.assertEqual(report.runs[0].timing_scope, "whole solver call (per run)")
        self.assertEqual(report.summaries[0].execution_metadata, (None, None))

    def test_available_execution_metadata_is_recorded_without_reinterpreting_scope(self):
        request = SolverRequest(QUBO(("x",), {}), validator=lambda _assignment: True)
        report = benchmark_qaoa_backends_repeated(
            "metadata-present", request,
            [_OneVariableQAOA(lambda _seed: 0, with_metadata=True)], seeds=(6,),
        )
        record = report.runs[0]
        self.assertEqual(record.execution_mode_detail, "local_simulator")
        self.assertEqual(record.execution_mode_source, "execution_metadata")
        self.assertEqual(record.timing_scope, "whole solver call (per run)")
        self.assertEqual(record.execution_metadata["backend_id"], "one-variable-qaoa")
        self.assertEqual(report.summaries[0].execution_metadata[0]["timing_scope"], "whole solver call")

    def test_seed_not_confirmed_by_adapter_makes_success_probability_unavailable(self):
        request = SolverRequest(
            QUBO(("x",), {}),
            validator=lambda _assignment: True,
            decoder=lambda assignment: dict(assignment),
            business_objective=lambda decoded: decoded["x"],
        )
        class UnseededQAOA(_OneVariableQAOA):
            def solve(self, request):
                from dataclasses import replace

                return replace(super().solve(request), random_seed=None)

        report = benchmark_qaoa_backends_repeated(
            "unseeded", request, [UnseededQAOA(lambda _seed: 0)], seeds=(9, 10),
        )
        self.assertEqual(report.summaries[0].seeded_run_count, 0)
        self.assertIsNone(report.summaries[0].optimal_feasible_success_probability)

    def test_repeated_runs_require_unique_explicit_integer_seeds(self):
        request = SolverRequest(QUBO(("x",), {}))
        solver = _OneVariableQAOA(lambda _seed: 0)
        with self.assertRaisesRegex(ValueError, "unique"):
            benchmark_qaoa_backends_repeated("bad", request, [solver], seeds=(1, 1))
        with self.assertRaisesRegex(TypeError, "integer"):
            benchmark_qaoa_backends_repeated("bad", request, [solver], seeds=(True,))

    def test_repeated_runs_reject_duplicate_solver_ids_before_executing(self):
        request = SolverRequest(QUBO(("x",), {}))
        first = _OneVariableQAOA(lambda _seed: 0)
        second = _OneVariableQAOA(lambda _seed: 1)
        with self.assertRaisesRegex(ValueError, "solver IDs must be unique"):
            benchmark_qaoa_backends_repeated(
                "duplicate-ids", request, [first, second], seeds=(1, 2)
            )
        self.assertEqual(first.seen_seeds, [])
        self.assertEqual(second.seen_seeds, [])


if __name__ == "__main__":
    unittest.main()
