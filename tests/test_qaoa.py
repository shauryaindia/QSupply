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
            {"first": Fraction(-1, 4), "late": Fraction(1, 2)},
            {("late", "first"): 1},
        )
        plan = build_qaoa_circuit_plan(ising, (0.25,), (0.1,))
        self.assertEqual(
            [(item.gate, item.qubits, item.angle) for item in plan],
            [
                ("h", (0,), None),
                ("h", (1,), None),
                ("rz", (0,), 0.25),
                ("rz", (1,), -0.125),
                ("rzz", (0, 1), 0.5),
                ("rx", (0,), 0.2),
                ("rx", (1,), 0.2),
            ],
        )
        no_offset = IsingModel(
            ising.variables, -1000, ising.linear, ising.quadratic
        )
        self.assertEqual(plan, build_qaoa_circuit_plan(no_offset, (0.25,), (0.1,)))
        self.assertEqual(ising.variable_indices, {"late": 0, "first": 1})

    def test_scaled_hamiltonian_rotations_keep_the_canonical_sign(self):
        ising = IsingModel(
            ("a", "b"),
            0,
            {"a": 4, "b": -2},
            {("a", "b"): 1},
        )
        plan = build_qaoa_circuit_plan(ising, (0.5,), (0.25,))
        rotations = [(item.gate, item.qubits, item.angle) for item in plan if item.angle is not None]
        self.assertEqual(
            rotations,
            [
                ("rz", (0,), 1.0),
                ("rz", (1,), -0.5),
                ("rzz", (0, 1), 0.25),
                ("rx", (0,), 0.5),
                ("rx", (1,), 0.5),
            ],
        )

    def test_qulacs_translation_negates_only_canonical_rotations(self):
        from qsupply.backends.qulacs import _append_operation

        class RecordingCircuit:
            def __init__(self):
                self.operations = []

            def add_H_gate(self, qubit):
                self.operations.append(("h", qubit))

            def add_RZ_gate(self, qubit, angle):
                self.operations.append(("rz", qubit, angle))

            def add_RX_gate(self, qubit, angle):
                self.operations.append(("rx", qubit, angle))

            def add_CNOT_gate(self, control, target):
                self.operations.append(("cx", control, target))

        circuit = RecordingCircuit()
        operations = build_qaoa_circuit_plan(
            IsingModel(("a", "b"), 0, {"a": 1, "b": 0}, {("a", "b"): 1}),
            (0.3,),
            (0.2,),
        )
        for operation in operations:
            _append_operation(circuit, operation)
        self.assertEqual(
            circuit.operations,
            [
                ("h", 0),
                ("h", 1),
                ("rz", 0, -0.6),
                ("cx", 0, 1),
                ("rz", 1, -0.6),
                ("cx", 0, 1),
                ("rx", 0, -0.4),
                ("rx", 1, -0.4),
            ],
        )

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
    def test_complete_qulacs_unitary_matches_canonical_qaoa_and_offset_phase(self):
        import numpy as np

        qulacs = __import__("qulacs")
        ising = IsingModel(
            ("x1", "x0"),
            Fraction(7, 3),
            {"x0": Fraction(-1, 2), "x1": Fraction(2, 3)},
            {("x1", "x0"): Fraction(5, 4)},
        )
        gamma = 0.37
        beta = 0.23
        plan = build_qaoa_circuit_plan(ising, (gamma,), (beta,))
        circuit = qulacs.QuantumCircuit(2)
        from qsupply.backends.qulacs import _append_operation

        for operation in plan:
            _append_operation(circuit, operation)
        actual = np.zeros((4, 4), dtype=complex)
        for column in range(4):
            state = qulacs.QuantumState(2)
            state.set_computational_basis(column)
            circuit.update_quantum_state(state)
            actual[:, column] = state.get_vector()

        scale = Fraction(5, 4)
        hadamard = np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2)
        h_initial = np.kron(hadamard, hadamard)
        cost_diagonal = []
        for raw in range(4):
            spins = {
                variable: 1 - 2 * ((raw >> index) & 1)
                for index, variable in enumerate(ising.variables)
            }
            variable_energy = ising.energy(spins) - ising.constant
            cost_diagonal.append(
                np.exp(-1j * gamma * float(variable_energy / scale))
            )
        cost = np.diag(cost_diagonal)
        mixer_single = np.cos(beta) * np.eye(2) - 1j * np.sin(beta) * np.array(
            [[0, 1], [1, 0]], dtype=complex
        )
        mixer = np.kron(mixer_single, mixer_single)
        canonical_without_offset = mixer @ cost @ h_initial
        np.testing.assert_allclose(actual, canonical_without_offset, atol=1e-12)

        # Including the Ising constant multiplies the complete unitary by one
        # scalar phase; it cannot change measurement probabilities.
        full_cost_diagonal = [
            np.exp(-1j * gamma * float(ising.energy({
                variable: 1 - 2 * ((raw >> index) & 1)
                for index, variable in enumerate(ising.variables)
            }) / scale))
            for raw in range(4)
        ]
        canonical_with_offset = mixer @ np.diag(full_cost_diagonal) @ h_initial
        global_phase = np.exp(-1j * gamma * float(ising.constant / scale))
        np.testing.assert_allclose(
            canonical_with_offset, global_phase * canonical_without_offset, atol=1e-12
        )
        np.testing.assert_allclose(
            canonical_with_offset, global_phase * actual, atol=1e-12
        )

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
        self.assertGreater(result.circuit_depth, config.depth)
        self.assertEqual(result.solver_id, "qulacs-qaoa")
        self.assertEqual(result.backend_version, QulacsBackend.version())
        self.assertEqual(result.full_energy, result.ising_energy)
        self.assertEqual(result.qubo_energy, -43)
        self.assertEqual(formulation.offset, 60)
        self.assertEqual(result.full_energy, formulation.offset + result.qubo_energy)
        self.assertEqual(result.full_energy, 17)
        self.assertEqual(exact.full_energy, 17)
        self.assertEqual(result.full_energy, exact.full_energy)
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
        self.assertIs(result.feasible, True)
        self.assertEqual(dict(result.decoded_solution), {"S1": "B", "S2": "A"})
        self.assertEqual(result.business_objective, 17)
        self.assertGreaterEqual(result.sample_count, result.best_sample_frequency)
        self.assertIsNotNone(result.average_sampled_energy)


if __name__ == "__main__":
    unittest.main()
