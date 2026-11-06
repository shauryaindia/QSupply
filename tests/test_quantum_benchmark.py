import unittest
from fractions import Fraction

from qsupply import QUBO, SolverRequest
from qsupply.quantum_benchmark import benchmark_qaoa_backends
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
        )


class TestQuantumBenchmark(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
