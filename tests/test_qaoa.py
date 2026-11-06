import cmath
import math
import unittest
from fractions import Fraction
from random import Random
from unittest.mock import patch

from qsupply import (
    IsingModel,
    QAOAConfig,
    QUBO,
    SampleBatch,
    SolverRequest,
    build_qaoa_circuit_plan,
    qubo_to_ising,
    run_qaoa,
)
from qsupply.backends.qulacs import (
    QulacsBackend,
    QulacsQAOASolver,
    decode_qulacs_samples,
)
from qsupply.solver import ExecutionStatus, ProblemRepresentation


class TestQAOAConfigurationAndPlan(unittest.TestCase):
    def test_configuration_limits_and_optimizer_validation(self):
        for kwargs in (
            {"depth": 0},
            {"depth": 4},
            {"shots": 15},
            {"shots": 2049},
            {"max_iterations": 0},
            {"max_iterations": 26},
            {"max_variables": 13},
            {"optimizer": "unknown"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises((TypeError, ValueError)):
                QAOAConfig(**kwargs)

    def test_standard_cost_then_mixer_plan_uses_variable_register_order(self):
        ising = IsingModel(
            ("late", "first"),
            100,
            {"late": 2, "first": 0},
            {("late", "first"): 3},
        )
        plan = build_qaoa_circuit_plan(ising, (0.25,), (0.1,))
        self.assertEqual(
            [(item.gate, item.qubits, item.angle) for item in plan],
            [
                ("h", (0,), None),
                ("h", (1,), None),
                ("rz", (0,), -1 / 3),
                ("cx", (0, 1), None),
                ("rz", (1,), -0.5),
                ("cx", (0, 1), None),
                ("rx", (0,), -0.2),
                ("rx", (1,), -0.2),
            ],
        )
        self.assertNotIn(100, [item.angle for item in plan])

    def test_qulacs_integer_sample_bit_order_is_little_endian(self):
        self.assertEqual(
            decode_qulacs_samples([0, 1, 2, 3, 1], 2),
            {(0, 0): 1, (1, 0): 2, (0, 1): 1, (1, 1): 1},
        )
        with self.assertRaises(ValueError):
            decode_qulacs_samples([4], 2)

    def test_sample_batch_validates_counts_and_immutability(self):
        batch = SampleBatch({(0, 1): 3, (1, 0): 1}, 0.001)
        self.assertEqual(batch.shots, 4)
        with self.assertRaises(TypeError):
            batch.counts[(0, 1)] = 5
        with self.assertRaises(ValueError):
            SampleBatch({(2,): 1}, 0.0)

    def test_backend_neutral_optimizer_is_seed_reproducible(self):
        ising = qubo_to_ising(
            QUBO(("x", "y"), {("x", "x"): -1, ("y", "y"): 2, ("x", "y"): -2})
        )

        def sampler(model, gammas, betas, shots, seed):
            del model, gammas, betas
            rng = Random(seed)
            counts = {}
            for _ in range(shots):
                bits = (rng.randrange(2), rng.randrange(2))
                counts[bits] = counts.get(bits, 0) + 1
            return SampleBatch(counts, 0.0)

        config = QAOAConfig(depth=1, optimizer="spsa", max_iterations=2, shots=16, random_seed=77)
        first = run_qaoa(ising, sampler, config)
        second = run_qaoa(ising, sampler, config)
        self.assertEqual(first.gammas, second.gammas)
        self.assertEqual(first.betas, second.betas)
        self.assertEqual(first.best_bits, second.best_bits)
        self.assertEqual(first.final_samples.counts, second.final_samples.counts)
        self.assertEqual(first.optimizer_iterations, 2)


class TestQulacsIntegration(unittest.TestCase):
    def test_missing_optional_package_returns_explicit_failed_result(self):
        request = SolverRequest(
            QUBO(("x",), {("x", "x"): 1}),
            representation=ProblemRepresentation.ISING,
        )
        solver = QulacsQAOASolver(
            QAOAConfig(depth=1, max_iterations=1, shots=16, random_seed=9)
        )
        with patch(
            "qsupply.backends.qulacs.importlib.import_module",
            side_effect=ImportError("simulated missing optional dependency"),
        ):
            result = solver.solve(request)
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIn("optional and is not installed", result.error)
        self.assertIsNone(result.best_binary_assignment)

    @unittest.skipUnless(QulacsBackend.is_available(), "optional Qulacs package not installed")
    def test_actual_qaoa_cost_circuit_matches_diagonal_hamiltonian(self):
        qulacs = __import__("qulacs")
        ising = IsingModel(
            ("x0", "x1"),
            Fraction(7, 3),
            {"x0": Fraction(2, 3), "x1": Fraction(-1, 2)},
            {("x0", "x1"): Fraction(5, 4)},
        )
        gamma = 0.37
        plan = build_qaoa_circuit_plan(ising, (gamma,), (0.0,))
        circuit = qulacs.QuantumCircuit(2)
        from qsupply.backends.qulacs import _append_operation

        for operation in plan:
            _append_operation(circuit, operation)
        state = qulacs.QuantumState(2)
        circuit.update_quantum_state(state)
        vector = state.get_vector()
        for raw in range(4):
            bits = tuple((raw >> index) & 1 for index in range(2))
            spins = {f"x{index}": 1 - 2 * bits[index] for index in range(2)}
            variable_energy = ising.energy(spins) - ising.constant
            expected = cmath.exp(
                -1j * gamma * float(variable_energy / Fraction(5, 4))
            ) / 2
            self.assertTrue(math.isclose(abs(vector[raw] - expected), 0, abs_tol=1e-10))

    @unittest.skipUnless(QulacsBackend.is_available(), "optional Qulacs package not installed")
    def test_seeded_qaoa_result_and_import_export_validation(self):
        from qsupply import ExactQUBOSolver, evaluate_business_objective
        from qsupply.import_export import (
            formulate_import_export_qubo,
            synthetic_import_export_problem,
        )

        problem = synthetic_import_export_problem()
        formulation = formulate_import_export_qubo(problem)
        request = SolverRequest(
            qubo=formulation.qubo,
            constant_offset=formulation.offset,
            representation=ProblemRepresentation.ISING,
            validator=formulation.check_feasibility,
            decoder=formulation.decode,
            business_objective=lambda selected: evaluate_business_objective(
                problem, selected
            ),
            random_seed=101,
        )
        config = QAOAConfig(depth=1, optimizer="spsa", max_iterations=2, shots=64, random_seed=101)
        solver = QulacsQAOASolver(config)
        result = solver.solve(request)
        repeated = solver.solve(request)
        exact = ExactQUBOSolver().solve(
            SolverRequest(
                formulation.qubo,
                constant_offset=formulation.offset,
                validator=formulation.check_feasibility,
                decoder=formulation.decode,
                business_objective=lambda selected: evaluate_business_objective(
                    problem, selected
                ),
            )
        )
        self.assertEqual(result.status, ExecutionStatus.COMPLETED)
        self.assertEqual(result.best_binary_assignment, repeated.best_binary_assignment)
        self.assertEqual(result.sample_frequencies, repeated.sample_frequencies)
        self.assertEqual(result.sample_count, 512)
        self.assertEqual(result.optimizer_iterations, 2)
        self.assertEqual(result.circuit_depth, 1)
        self.assertEqual(result.solver_id, "qulacs-qaoa")
        self.assertEqual(result.backend_version, QulacsBackend.version())
        self.assertEqual(result.full_energy, result.ising_energy)
        self.assertEqual(exact.full_energy, 17)
        self.assertGreaterEqual(result.full_energy, exact.full_energy)
        feasible_samples = sum(
            count
            for bits, count in result.sample_frequencies.items()
            if formulation.check_feasibility(
                dict(zip(formulation.qubo.variables, bits))
            ).feasible
        )
        self.assertLessEqual(feasible_samples, result.sample_count)
        self.assertEqual(
            result.feasible_sample_rate,
            feasible_samples / sum(result.sample_frequencies.values()),
        )
        self.assertIsInstance(result.feasible, bool)
        if result.feasible:
            self.assertIsNotNone(result.decoded_solution)
            self.assertIsNotNone(result.business_objective)
        self.assertGreaterEqual(result.sample_count, result.best_sample_frequency)
        self.assertIsNotNone(result.average_sampled_energy)


if __name__ == "__main__":
    unittest.main()
