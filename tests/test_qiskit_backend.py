import unittest
from fractions import Fraction
from itertools import product
from unittest.mock import patch

from qsupply import (
    IsingModel,
    QAOAConfig,
    QUBO,
    SolverRequest,
    benchmark_qaoa_backends,
    qubo_to_ising,
)
from qsupply.backends.qiskit import (
    QiskitBackend,
    QiskitQAOASolver,
    build_qiskit_qaoa_circuit,
    decode_qiskit_counts,
)
from qsupply.import_export import (
    evaluate_business_objective,
    formulate_import_export_qubo,
    synthetic_import_export_problem,
)
from qsupply.solver import ExecutionStatus, ProblemRepresentation


class TestQiskitCountDecoding(unittest.TestCase):
    def test_single_and_multi_qubit_register_order(self):
        self.assertEqual(decode_qiskit_counts({"1": 3, "0": 1}, 1), {(1,): 3, (0,): 1})
        self.assertEqual(
            decode_qiskit_counts({"100": 2, "0 11": 4}, 3),
            {(0, 0, 1): 2, (1, 1, 0): 4},
        )
        self.assertEqual(
            decode_qiskit_counts({"100": 1}, 3)[(0, 0, 1)], 1
        )

    def test_invalid_counts_are_rejected(self):
        for counts, width in (({"2": 1}, 1), ({"10": 1}, 1), ({"0": 0}, 1)):
            with self.subTest(counts=counts), self.assertRaises(ValueError):
                decode_qiskit_counts(counts, width)

    def test_missing_optional_sdk_returns_clear_failed_solver_result(self):
        request = SolverRequest(
            QUBO(("x",), {("x", "x"): -1}),
            representation=ProblemRepresentation.ISING,
        )
        solver = QiskitQAOASolver(
            QAOAConfig(depth=1, max_iterations=1, shots=16, random_seed=7)
        )
        with patch(
            "qsupply.backends.qiskit.importlib.import_module",
            side_effect=ImportError("simulated missing optional dependency"),
        ):
            result = solver.solve(request)
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIn("Qiskit SDK 2.x is an optional dependency", result.error)
        self.assertIsNone(result.best_binary_assignment)


@unittest.skipUnless(QiskitBackend.is_available(), "optional Qiskit SDK not installed")
class TestQiskitIntegration(unittest.TestCase):
    def test_parameterized_circuit_uses_canonical_rotations_and_register_order(self):
        import numpy as np

        qubo = QUBO(
            ("late", "first"),
            {
                ("late", "late"): Fraction(1, 2),
                ("first", "first"): Fraction(-1, 4),
                ("late", "first"): Fraction(3, 2),
                ("first", "late"): Fraction(1, 4),
            },
        )
        offset = Fraction(11, 7)
        ising = qubo_to_ising(qubo, offset=offset)
        circuit, (gammas, betas) = build_qiskit_qaoa_circuit(ising, 1)
        self.assertEqual(tuple(map(str, gammas)), ("gamma[0]",))
        self.assertEqual(tuple(map(str, betas)), ("beta[0]",))
        self.assertEqual(circuit.num_qubits, 2)
        self.assertEqual(ising.variable_indices, {"late": 0, "first": 1})
        bound = circuit.assign_parameters({gammas[0]: 0.37, betas[0]: 0.23})
        from qiskit.quantum_info import Operator

        actual = Operator(bound.remove_final_measurements(inplace=False)).data

        hadamard = np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2)
        initial = np.kron(hadamard, hadamard)
        scale = max(
            abs(value) for value in (*ising.linear.values(), *ising.quadratic.values())
        )
        diagonal = []
        for raw in range(4):
            bits = tuple((raw >> index) & 1 for index in range(2))
            assignment = dict(zip(ising.variables, bits, strict=True))
            spins = {name: 1 - 2 * bits[index] for index, name in enumerate(ising.variables)}
            self.assertEqual(ising.energy(spins), offset + qubo.energy(assignment))
            diagonal.append(np.exp(-1j * 0.37 * float((ising.energy(spins) - ising.constant) / scale)))
        cost = np.diag(diagonal)
        mixer_single = np.cos(0.23) * np.eye(2) - 1j * np.sin(0.23) * np.array(
            [[0, 1], [1, 0]], dtype=complex
        )
        expected = np.kron(mixer_single, mixer_single) @ cost @ initial
        np.testing.assert_allclose(actual, expected, atol=1e-12)

    def test_seeded_sampling_is_reproducible_and_preserves_variable_order(self):
        ising = IsingModel(("v2", "v0", "v1"), 9, {"v2": 1, "v0": -2, "v1": 3}, {})
        backend = QiskitBackend()
        first = backend.sample(ising, (0.4,), (0.2,), 64, 991)
        second = backend.sample(ising, (0.4,), (0.2,), 64, 991)
        self.assertEqual(first.counts, second.counts)
        self.assertEqual(first.shots, 64)
        self.assertTrue(all(len(bits) == 3 for bits in first.counts))

    def test_solver_recomputes_qubo_ising_and_full_energy_and_validates_plan(self):
        problem = synthetic_import_export_problem()
        formulation = formulate_import_export_qubo(problem)
        request = SolverRequest(
            qubo=formulation.qubo,
            constant_offset=formulation.offset,
            representation=ProblemRepresentation.ISING,
            validator=formulation.check_feasibility,
            decoder=formulation.decode,
            business_objective=lambda selections: evaluate_business_objective(problem, selections),
            random_seed=19,
        )
        result = QiskitQAOASolver(
            QAOAConfig(depth=1, max_iterations=1, shots=32, random_seed=19)
        ).solve(request)
        self.assertEqual(result.status, ExecutionStatus.COMPLETED, result.error)
        self.assertEqual(result.variable_order, formulation.qubo.variables)
        self.assertEqual(result.full_energy, result.qubo_energy + formulation.offset)
        self.assertEqual(result.full_energy, result.ising_energy)
        self.assertEqual(
            result.qubo_energy,
            formulation.qubo.energy(result.best_binary_assignment),
        )
        self.assertEqual(
            result.ising_energy,
            request.ising_model.energy(result.best_spin_assignment),
        )
        if result.feasible:
            self.assertEqual(result.business_objective, 17)

    def test_real_backend_benchmark_shares_exact_problem_and_full_energy(self):
        from qsupply.backends.qulacs import QulacsBackend, QulacsQAOASolver

        problem = synthetic_import_export_problem()
        formulation = formulate_import_export_qubo(problem)
        request = SolverRequest(
            qubo=formulation.qubo,
            constant_offset=formulation.offset,
            validator=formulation.check_feasibility,
            decoder=formulation.decode,
            business_objective=lambda choices: evaluate_business_objective(problem, choices),
            random_seed=317,
        )
        config = QAOAConfig(depth=1, max_iterations=1, shots=32, random_seed=317)
        solvers = [QiskitQAOASolver(config)]
        if QulacsBackend.is_available():
            solvers.append(QulacsQAOASolver(config))
        records = benchmark_qaoa_backends("synthetic-import-export", request, solvers)
        self.assertEqual(records[0].exact_optimum, 17)
        self.assertEqual(records[0].best_sampled_energy, 17)
        self.assertEqual(records[0].best_sample_feasible, True)
        for record in records[1:]:
            self.assertEqual(record.problem_id, "synthetic-import-export")
            self.assertEqual(record.variable_count, len(formulation.qubo.variables))
            self.assertEqual(record.qaoa_depth, 1)
            self.assertEqual(record.shots, 32)
            self.assertEqual(record.optimizer_iterations, 1)
            self.assertEqual(record.random_seed, 317)
            self.assertEqual(record.exact_optimum, 17)
            self.assertIsNotNone(record.best_sampled_energy)
            self.assertGreaterEqual(record.best_sampled_energy, 17)
            self.assertEqual(
                record.absolute_energy_gap,
                record.best_sampled_energy - record.exact_optimum,
            )
            if record.best_sample_feasible:
                self.assertGreaterEqual(record.business_objective, 17)

    def test_qaoa_unitary_agrees_with_qulacs_when_both_optional_sdks_exist(self):
        from qsupply.backends.qulacs import QulacsBackend, _append_operation

        if not QulacsBackend.is_available():
            self.skipTest("optional Qulacs package not installed in this environment")
        import numpy as np
        import qulacs

        ising = IsingModel(("x0", "x1"), Fraction(5, 4), {"x0": 1, "x1": -2}, {("x0", "x1"): 3})
        gamma, beta = 0.31, 0.17
        plan = __import__("qsupply").build_qaoa_circuit_plan(ising, (gamma,), (beta,))
        qulacs_circuit = qulacs.QuantumCircuit(2)
        for operation in plan:
            _append_operation(qulacs_circuit, operation)
        qiskit_circuit, (gammas, betas) = build_qiskit_qaoa_circuit(ising, 1)
        qiskit_circuit = qiskit_circuit.assign_parameters({gammas[0]: gamma, betas[0]: beta})
        from qiskit.quantum_info import Operator

        qiskit_unitary = Operator(qiskit_circuit.remove_final_measurements(inplace=False)).data
        qulacs_unitary = np.zeros((4, 4), dtype=complex)
        for column in range(4):
            state = qulacs.QuantumState(2)
            state.set_computational_basis(column)
            qulacs_circuit.update_quantum_state(state)
            qulacs_unitary[:, column] = state.get_vector()
        np.testing.assert_allclose(qiskit_unitary, qulacs_unitary, atol=1e-12)


if __name__ == "__main__":
    unittest.main()
