from __future__ import annotations

import csv
import json
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch
from fractions import Fraction

from qsupply.backends.qiskit import QiskitBackend, QiskitQAOASolver
from qsupply.backends.qulacs import QulacsBackend
from qsupply.backends.registry import QuantumBackendRegistration, QuantumBackendRegistry
from qsupply.execution import ExecutionMode
from qsupply.network import ObjectiveWeights
from qsupply.network.route_qubo_experiments import (
    ExperimentConfiguration,
    _aggregate_runs,
    RouteExperimentSpec,
    export_experiment_report,
    run_route_experiments,
)
from qsupply.solver import BackendType, ProblemRepresentation


class TestRouteQUBOExperiments(unittest.TestCase):
    def test_configuration_is_immutable_and_fingerprinted(self):
        candidates = {"routes": ["r1", "r2"]}
        config = ExperimentConfiguration.create(
            problem_id="p", problem_size=1, qubo_variable_count=2,
            objective_profile="test",
            candidate_generation=candidates, objective_weights={"cost": 100},
            penalty_configuration={"value": "5"}, constant_offset="-2",
            backend="exact", qaoa={}, random_seed=11,
            software_versions={"python": "3.x"}, problem_fingerprint="a" * 64,
        )
        candidates["routes"].append("r3")
        self.assertEqual(config.candidate_generation["routes"], ("r1", "r2"))
        with self.assertRaises(TypeError):
            config.candidate_generation["routes"] = ()
        self.assertEqual(len(config.configuration_id), 64)

    def test_exact_and_classical_share_validated_problem_and_energy(self):
        report = run_route_experiments(
            specs=(RouteExperimentSpec("small", ("EXP-104", "EXP-407")),),
            weights_by_profile={"balanced": ObjectiveWeights()},
            backends=(), seeds=(7,),
        )
        self.assertEqual(len(report.runs), 2)
        exact, classical = report.runs
        self.assertTrue(exact.feasible)
        self.assertTrue(classical.feasible)
        self.assertEqual(Fraction(exact.qubo_energy) + Fraction(exact.constant_offset), Fraction(exact.ising_energy))
        self.assertEqual(exact.full_penalized_energy, exact.ising_energy)
        self.assertEqual(exact.configuration.problem_fingerprint,
                         classical.configuration.problem_fingerprint)
        self.assertEqual(exact.configuration.qubo_variable_count, 8)
        self.assertEqual(report.manifest["instances"][0]["variables"], 8)

    def test_unavailable_backend_is_recorded_without_fallback(self):
        registry = QuantumBackendRegistry()
        registry.register(QuantumBackendRegistration(
            backend_id="test-offline", name="Offline", description="test",
            backend_type=BackendType.SIMULATOR,
            supported_representations=(ProblemRepresentation.ISING,),
            execution_mode=ExecutionMode.LOCAL_SIMULATOR,
            optional_dependency="optional", dependency_requirements="test",
            availability_check=lambda: False, version_check=lambda: None,
            solver_factory=lambda config: None,
            supported_configuration={"depth": {"minimum": 1, "maximum": 1}},
        ))
        report = run_route_experiments(
            specs=(RouteExperimentSpec("small", ("EXP-104", "EXP-407")),),
            weights_by_profile={"balanced": ObjectiveWeights()},
            backends=("test-offline",), seeds=(7, 9), registry=registry,
        )
        rows = [run for run in report.runs if run.solver == "test-offline"]
        self.assertEqual([row.status for row in rows], ["unavailable", "unavailable"])
        self.assertTrue(all(row.execution_time_seconds is None for row in rows))
        self.assertTrue(any(row.solver == "exact-qubo" for row in report.runs))

    @unittest.skipUnless(QiskitBackend.is_available(), "Qiskit SDK required")
    def test_middle_seed_exception_continues_or_marks_pending_trial_not_run(self):
        solve = QiskitQAOASolver.solve
        for stop in (False, True):
            calls = []
            def inject(solver, request):
                calls.append(request.random_seed)
                if request.random_seed == 22:
                    raise RuntimeError("seed 22 injected error")
                return solve(solver, request)
            with self.subTest(stop=stop), patch.object(QiskitQAOASolver, "solve", inject):
                report = run_route_experiments(
                    specs=(RouteExperimentSpec("middle", ("EXP-104", "EXP-407")),),
                    weights_by_profile={"balanced": ObjectiveWeights()}, backends=("qiskit",),
                    seeds=(11, 22, 33), iterations=1, shots=16, stop_backend_on_failure=stop,
                )
                rows = [r for r in report.runs if r.solver == "qiskit"]
                self.assertEqual([r.configuration.random_seed for r in rows], [11, 22, 33])
                self.assertEqual([r.status for r in rows], ["completed", "failed", "not_run" if stop else "completed"])
                self.assertEqual(calls, [11, 22] if stop else [11, 22, 33])
                self.assertIsNotNone(rows[0].assignment)
                self.assertEqual(rows[1].backend_metadata["error"], "seed 22 injected error")
                self.assertIsNotNone(rows[1].execution_time_seconds)
                for row in rows[1:3 if stop else 2]:
                    self.assertIsNone(row.assignment)
                    self.assertIsNone(row.feasible)
                    self.assertIsNone(row.full_penalized_energy)
                    self.assertIsNone(row.business_objective)
                if stop:
                    self.assertIsNone(rows[2].execution_time_seconds)
                else:
                    self.assertIsNotNone(rows[2].assignment)

    def test_summary_matches_exact_values_without_using_gap(self):
        report = run_route_experiments(
            specs=(RouteExperimentSpec("small", ("EXP-104",)),),
            weights_by_profile={"balanced": ObjectiveWeights()}, backends=(), seeds=(11,),
        )
        exact = report.runs[0]
        for reference, feasible, value, expected in (
            ("0", True, "0", 1), ("0", True, "1", 0),
            ("2/3", True, "2/3", 1), ("2/3", True, "20000000000000001/30000000000000000", 0),
            (None, False, None, None), (None, True, "1", None),
        ):
            reference_row = replace(exact, feasible=feasible, business_objective=reference)
            trial = replace(exact, solver="qiskit", feasible=feasible, business_objective=value,
                            optimal_feasible_gap_percent=None, backend_metadata={"seed_applied": True})
            summary = _aggregate_runs((reference_row, trial))[-1]
            self.assertEqual(summary["optimal_feasible_success_probability"], expected)

    @unittest.skipUnless(QiskitBackend.is_available(), "Qiskit SDK required")
    def test_proven_infeasible_has_no_success_rate_in_either_summary(self):
        report = run_route_experiments(
            specs=(RouteExperimentSpec("portfolio-15", ("EXP-104", "EXP-205", "EXP-508"),
                                       2, "synthetic-suez-capacity-restriction"),),
            weights_by_profile={"balanced": ObjectiveWeights()}, backends=("qiskit",),
            seeds=(11,), iterations=1, shots=16,
        )
        self.assertFalse(report.runs[0].feasible)
        for summary in report.summaries:
            self.assertIsNone(summary["optimal_feasible_success_probability"])

    def test_unknown_backend_is_rejected(self):
        with self.assertRaises(KeyError):
            run_route_experiments(backends=("not-registered",))

    def test_json_and_csv_exports_preserve_individual_results(self):
        report = run_route_experiments(
            specs=(RouteExperimentSpec("small", ("EXP-104", "EXP-407")),),
            weights_by_profile={"balanced": ObjectiveWeights()},
            backends=(), seeds=(7,),
        )
        with tempfile.TemporaryDirectory() as temporary:
            manifest, runs, summary = export_experiment_report(report, temporary)
            self.assertEqual(json.loads(manifest.read_text())["schema_version"], 1)
            exported_runs = json.loads(runs.read_text())
            self.assertEqual(len(exported_runs), 2)
            instance = json.loads(manifest.read_text())["instances"][0]
            with summary.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
                self.assertEqual(len(rows), 2)
                for field in ("domain_fingerprint", "qubo_fingerprint"):
                    self.assertRegex(instance[field], r"^[0-9a-f]{64}$")
                    self.assertTrue(all(r[field] == instance[field] for r in rows + exported_runs))
                self.assertEqual(rows[0]["mean_full_energy_exact"], rows[0]["best_full_energy"])
            with self.assertRaises(FileExistsError):
                export_experiment_report(report, temporary)

    @unittest.skipUnless(
        QiskitBackend.is_available() and QulacsBackend.is_available(),
        "Qiskit 2.x and Qulacs 0.6.x are required for SDK execution coverage",
    )
    def test_sdk_backends_execute_and_are_rescored_by_experiment_harness(self):
        report = run_route_experiments(
            specs=(RouteExperimentSpec("small", ("EXP-104", "EXP-407")),),
            weights_by_profile={"balanced": ObjectiveWeights()},
            backends=("qiskit", "qulacs"), seeds=(11, 22),
            depth=1, optimizer="spsa", iterations=1, shots=16,
        )
        quantum_runs = [run for run in report.runs if run.solver in {"qiskit", "qulacs"}]
        self.assertEqual(len(quantum_runs), 4)
        for run in quantum_runs:
            self.assertEqual(run.status, "completed")
            self.assertIsNotNone(run.assignment)
            self.assertEqual(Fraction(run.qubo_energy) + Fraction(run.constant_offset),
                             Fraction(run.ising_energy))
            self.assertEqual(run.full_penalized_energy, run.ising_energy)
            self.assertEqual(run.configuration.random_seed, run.backend_metadata["requested_seed"])
            if run.feasible:
                self.assertIsNotNone(run.selected_routes)
                self.assertIsNotNone(run.business_objective)
            else:
                self.assertIsNone(run.business_objective)
                self.assertIsNone(run.optimal_feasible_gap_percent)


if __name__ == "__main__":
    unittest.main()
