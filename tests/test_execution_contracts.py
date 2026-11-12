from fractions import Fraction
import unittest

from qsupply import (
    ExecutionErrorCategory,
    ExecutionMetadata,
    ExecutionMode,
    ExecutionTimings,
    QAOAConfig,
    ProblemRepresentation,
    QUBO,
    SolverRequest,
    classify_execution_error,
    qubo_to_ising,
    recompute_sample_energies,
)
from qsupply.backends.qulacs import QulacsQAOASolver
from qsupply.qaoa import SampleBatch


class TestExecutionMetadata(unittest.TestCase):
    def test_unavailable_stage_timings_remain_unknown(self):
        metadata = ExecutionMetadata(
            backend_id="local-test",
            backend_name="Local test backend",
            execution_mode=ExecutionMode.LOCAL_SIMULATOR,
            timing_scope="backend_sample_call_wall_time",
            timings=ExecutionTimings(),
        )
        self.assertIsNone(metadata.timings.submission_seconds)
        self.assertIsNone(metadata.timings.queue_seconds)
        self.assertIsNone(metadata.timings.remote_execution_seconds)
        self.assertIsNone(metadata.timings.result_retrieval_seconds)

    def test_measured_stage_timings_and_immutable_attributes(self):
        metadata = ExecutionMetadata(
            backend_id="remote-test",
            backend_name="Remote test backend",
            execution_mode=ExecutionMode.REMOTE_SIMULATOR,
            timings=ExecutionTimings(
                submission_seconds=0.1,
                queue_seconds=0.2,
                remote_execution_seconds=0.3,
                result_retrieval_seconds=0.4,
            ),
            attributes={"region": "test"},
        )
        self.assertEqual(metadata.timings.queue_seconds, 0.2)
        with self.assertRaises(TypeError):
            metadata.attributes["region"] = "changed"

    def test_invalid_timing_values_are_rejected(self):
        for value in (-0.1, float("nan"), float("inf"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ExecutionTimings(queue_seconds=value)

    def test_errors_map_to_stable_backend_neutral_categories(self):
        cases = (
            (ImportError("missing"), True, ExecutionErrorCategory.UNAVAILABLE_DEPENDENCY),
            (ValueError("bad option"), False, ExecutionErrorCategory.EXECUTION_FAILURE),
            (TypeError("SDK rejected a runtime value"), False, ExecutionErrorCategory.EXECUTION_FAILURE),
            (RuntimeError("failed"), False, ExecutionErrorCategory.EXECUTION_FAILURE),
            (TimeoutError("late"), False, ExecutionErrorCategory.TIMEOUT),
        )
        for error, unavailable, expected in cases:
            with self.subTest(expected=expected):
                detail = classify_execution_error(
                    error, unavailable_dependency=unavailable
                )
                self.assertEqual(detail.category, expected)
                self.assertEqual(detail.message, str(error))
                self.assertEqual(detail.exception_type, type(error).__name__)

    def test_configuration_category_requires_explicit_classification(self):
        detail = classify_execution_error(
            ValueError("invalid QAOA setting"), invalid_configuration=True
        )
        self.assertEqual(detail.category, ExecutionErrorCategory.INVALID_CONFIGURATION)


class TestSampleEnergyRecomputation(unittest.TestCase):
    def test_every_sample_energy_is_recomputed_from_qubo_ising_and_offset(self):
        qubo = QUBO(
            ("second", "first"),
            {
                ("second", "second"): Fraction(3, 2),
                ("first", "first"): Fraction(-2, 3),
                ("second", "first"): Fraction(5, 4),
                ("first", "second"): Fraction(-1, 4),
            },
        )
        offset = Fraction(7, 5)
        request = SolverRequest(qubo, constant_offset=offset)
        counts = {(0, 1): 3, (1, 0): 2, (1, 1): 1}

        records = recompute_sample_energies(request, counts)
        self.assertEqual(set(records), set(counts))
        for bits, record in records.items():
            assignment = dict(zip(request.variable_order, bits, strict=True))
            spins = {name: 1 - 2 * assignment[name] for name in request.variable_order}
            self.assertEqual(record.qubo_energy, qubo.energy(assignment))
            self.assertEqual(record.full_energy, offset + qubo.energy(assignment))
            self.assertEqual(
                record.ising_energy, qubo_to_ising(qubo, offset=offset).energy(spins)
            )
            self.assertEqual(record.full_energy, record.ising_energy)
            self.assertEqual(record.frequency, counts[bits])

    def test_malformed_sample_bits_and_frequencies_are_rejected(self):
        request = SolverRequest(QUBO(("x",), {("x", "x"): 1}))
        with self.assertRaisesRegex(ValueError, "match variable_order"):
            recompute_sample_energies(request, {(0, 1): 1})
        with self.assertRaisesRegex(ValueError, "positive integers"):
            recompute_sample_energies(request, {(0,): 0})

    def test_solver_result_contains_qsupply_recomputed_energy_for_each_final_sample(self):
        class FixedBackend:
            name = "Fixed backend"

            @staticmethod
            def version():
                return "test"

            def sample(self, request):
                return SampleBatch(
                    {(0,): request.shots},
                    0.001,
                    variable_order=request.variable_order,
                    backend_id="fixed",
                    backend_name=self.name,
                    backend_version=self.version(),
                    requested_shots=request.shots,
                    seed=request.seed,
                    execution_metadata=ExecutionMetadata(
                        backend_id="fixed",
                        backend_name=self.name,
                        backend_version=self.version(),
                        execution_mode=ExecutionMode.LOCAL_SIMULATOR,
                        timing_scope="backend_sample_call_wall_time",
                    ),
                )

            @staticmethod
            def circuit_depth(ising, depth):
                return depth

        qubo = QUBO(("x",), {("x", "x"): -3})
        request = SolverRequest(
            qubo,
            constant_offset=5,
            representation=ProblemRepresentation.ISING,
        )
        result = QulacsQAOASolver(
            QAOAConfig(depth=1, max_iterations=1, shots=16), backend=FixedBackend()
        ).solve(request)
        self.assertEqual(result.status.value, "completed")
        self.assertEqual(len(result.sample_energies), 1)
        record = result.sample_energies[(0,)]
        self.assertEqual(record.qubo_energy, 0)
        self.assertEqual(record.full_energy, 5)
        self.assertEqual(record.ising_energy, 5)
        self.assertEqual(record.frequency, 16)
        self.assertEqual(result.execution_metadata.backend_id, "fixed")
        self.assertEqual(result.average_sampled_energy, 5)

    def test_solver_result_error_categories_cover_config_execution_and_timeout(self):
        class RaisingBackend:
            name = "Raising backend"

            def __init__(self, error):
                self.error = error

            @staticmethod
            def version():
                return "test"

            def sample(self, request):
                raise self.error

        request = SolverRequest(
            QUBO(("x",), {("x", "x"): 1}),
            representation=ProblemRepresentation.ISING,
        )
        cases = (
            (ValueError("SDK runtime failure"), ExecutionErrorCategory.EXECUTION_FAILURE),
            (TypeError("SDK runtime type failure"), ExecutionErrorCategory.EXECUTION_FAILURE),
            (RuntimeError("backend failed"), ExecutionErrorCategory.EXECUTION_FAILURE),
            (TimeoutError("timed out"), ExecutionErrorCategory.TIMEOUT),
        )
        for error, expected in cases:
            with self.subTest(expected=expected):
                result = QulacsQAOASolver(
                    QAOAConfig(depth=1, max_iterations=1, shots=16),
                    backend=RaisingBackend(error),
                ).solve(request)
                self.assertEqual(result.error_details.category, expected)


if __name__ == "__main__":
    unittest.main()
