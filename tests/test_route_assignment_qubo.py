from itertools import product
import unittest

from qsupply.network import ObjectiveWeights
from qsupply.network.global_demo import global_demo_network
from qsupply.network.routing import generate_candidate_routes
from qsupply.network.route_qubo import (
    UnsupportedRouteQUBOError,
    formulate_route_assignment_qubo,
)
from qsupply.network.route_qubo_demo import (
    ROUTE_QUBO_DEMO_SCENARIO,
    build_route_qubo_demo,
    compare_route_qubo_to_classical,
)
from qsupply.backends.qiskit import QiskitBackend, QiskitQAOASolver
from qsupply.backends.qulacs import QulacsBackend, QulacsQAOASolver
from qsupply.qaoa import QAOAConfig
from qsupply.solver import ExactQUBOSolver, ExecutionStatus, ProblemRepresentation


class TestRouteAssignmentQUBO(unittest.TestCase):
    def setUp(self):
        self.formulation, self.comparison = build_route_qubo_demo()

    def assignment_for(self, selection, *, slack_bits=None):
        bits = {variable: 0 for variable in self.formulation.variable_order}
        for shipment_id, route_id in selection.items():
            bits[self.formulation.route_variables[(shipment_id, route_id)]] = 1
        if slack_bits:
            bits.update(slack_bits)
        return bits

    def test_deterministic_variable_order_and_slack_encoding(self):
        duplicate, _ = build_route_qubo_demo()
        self.assertEqual(self.formulation.variable_order, duplicate.variable_order)
        self.assertEqual(self.formulation.decision_variable_count, 6)
        self.assertEqual(self.formulation.slack_variable_count, 2)
        self.assertEqual(self.formulation.variable_count, 8)
        self.assertEqual(
            self.formulation.slack_variables["road-shanghai-port"],
            (("slack_l0_b0", 1), ("slack_l0_b1", 2)),
        )

    def test_valid_route_assignment_decodes_and_reports_capacity(self):
        selection = {
            profile.request.id: routes[0].id
            for profile_id, routes in self.comparison.recovery_candidates.items()
            for profile in self.formulation.profiles
            if profile.request.id == profile_id
        }
        # Use one route that avoids the constrained port and one route through it.
        selection["EXP-104"] = self.comparison.recovery_candidates["EXP-104"][2].id
        selection["EXP-407"] = self.comparison.recovery_candidates["EXP-407"][0].id
        report = self.formulation.check_plan(selection)
        self.assertTrue(report.feasible, report.violations)
        self.assertEqual(self.formulation.decode(self.assignment_for(selection)), selection)
        self.assertEqual(report.capacity_usage["road-shanghai-port"], 2)
        self.assertAlmostEqual(report.capacity_utilization["road-shanghai-port"], 2 / 3)

    def test_shared_capacity_violation_is_independently_detected(self):
        selection = {
            shipment_id: routes[0].id
            for shipment_id, routes in self.comparison.recovery_candidates.items()
        }
        report = self.formulation.check_plan(selection)
        self.assertFalse(report.feasible)
        self.assertTrue(any("shared capacity exceeded" in item for item in report.violations))
        with self.assertRaisesRegex(ValueError, "infeasible route assignment"):
            self.formulation.decode(self.assignment_for(selection))

    def test_missing_unknown_and_incompatible_route_selections_are_reported(self):
        routes = self.comparison.recovery_candidates
        missing = self.formulation.check_plan({"EXP-104": routes["EXP-104"][0].id})
        self.assertFalse(missing.feasible)
        self.assertTrue(any("missing shipments" in item for item in missing.violations))
        unknown = self.formulation.check_plan(
            {"EXP-104": "bad-route", "EXP-407": routes["EXP-407"][0].id}
        )
        self.assertFalse(unknown.feasible)
        self.assertTrue(any("unknown route" in item for item in unknown.violations))
        extra = self.formulation.check_plan(
            {
                "EXP-104": routes["EXP-104"][0].id,
                "EXP-407": routes["EXP-407"][0].id,
                "EXP-999": "route",
            }
        )
        self.assertFalse(extra.feasible)
        self.assertTrue(any("unknown shipments" in item for item in extra.violations))

    def test_assignment_requires_complete_binary_values_and_one_hot_choices(self):
        selection = {
            "EXP-104": self.comparison.recovery_candidates["EXP-104"][2].id,
            "EXP-407": self.comparison.recovery_candidates["EXP-407"][0].id,
        }
        assignment = self.assignment_for(selection)
        self.assertTrue(self.formulation.validate_assignment(assignment).feasible)
        incomplete = dict(assignment)
        incomplete.pop(self.formulation.variable_order[0])
        with self.assertRaisesRegex(ValueError, "missing variables"):
            self.formulation.validate_assignment(incomplete)
        invalid = dict(assignment)
        invalid[self.formulation.variable_order[0]] = 2
        with self.assertRaisesRegex(ValueError, "must be 0 or 1"):
            self.formulation.validate_assignment(invalid)
        multiple = dict(assignment)
        second = self.comparison.recovery_candidates["EXP-104"][0].id
        multiple[self.formulation.route_variables[("EXP-104", second)]] = 1
        self.assertFalse(self.formulation.validate_assignment(multiple).feasible)

    def test_exhaustive_energy_decomposition_and_infeasibility_penalty_bound(self):
        feasible_energy_values = []
        assignment_count = 0
        for values in product((0, 1), repeat=self.formulation.variable_count):
            assignment = dict(zip(self.formulation.variable_order, values, strict=True))
            evaluation = self.formulation.evaluate_assignment(assignment)
            assignment_count += 1
            self.assertEqual(
                evaluation.full_penalized_energy,
                evaluation.objective_contribution + evaluation.penalty_contribution,
            )
            self.assertEqual(
                evaluation.full_penalized_energy,
                self.formulation.offset + self.formulation.qubo.energy(assignment),
            )
            self.assertEqual(
                self.formulation.solver_request(ProblemRepresentation.QUBO).qubo.energy(assignment),
                self.formulation.qubo.energy(assignment),
            )
            if evaluation.feasibility.feasible and evaluation.penalty_contribution == 0:
                feasible_energy_values.append(evaluation.full_penalized_energy)
        self.assertEqual(assignment_count, 256)
        self.assertTrue(feasible_energy_values)
        best_feasible = min(feasible_energy_values)
        for values in product((0, 1), repeat=self.formulation.variable_count):
            assignment = dict(zip(self.formulation.variable_order, values, strict=True))
            evaluation = self.formulation.evaluate_assignment(assignment)
            if not evaluation.feasibility.feasible:
                self.assertGreater(evaluation.full_penalized_energy, best_feasible)

    def test_business_objective_is_separate_from_penalties_and_offset(self):
        selection = {
            "EXP-104": self.comparison.recovery_candidates["EXP-104"][2].id,
            "EXP-407": self.comparison.recovery_candidates["EXP-407"][0].id,
        }
        assignment = self.assignment_for(selection)
        # The equality slack needs to encode capacity 1 for the used shared link.
        assignment["slack_l0_b0"] = 1
        assignment["slack_l0_b1"] = 0
        evaluated = self.formulation.evaluate_assignment(assignment)
        self.assertTrue(evaluated.feasibility.feasible)
        self.assertEqual(evaluated.penalty_contribution, 0)
        self.assertIsNotNone(evaluated.business_metrics)
        self.assertEqual(
            evaluated.objective_contribution,
            evaluated.business_metrics.weighted_objective,
        )
        self.assertEqual(
            evaluated.full_penalized_energy,
            evaluated.business_metrics.weighted_objective,
        )

    def test_exact_qubo_and_classical_assignment_agree_on_same_candidates(self):
        result = compare_route_qubo_to_classical()
        self.assertEqual(result.exact_result.status, ExecutionStatus.COMPLETED)
        self.assertTrue(result.exact_result.feasible)
        self.assertTrue(result.same_objective)
        exact_plan = result.formulation.decode(result.exact_result.best_binary_assignment)
        classical_plan = {
            shipment_id: route.id
            for shipment_id, route in result.classical_result.routes.items()
        }
        self.assertAlmostEqual(
            float(result.formulation.evaluate_business_objective(exact_plan).weighted_objective),
            result.classical_result.metrics.weighted_objective,
            places=12,
        )

    def test_objective_weight_change_can_change_the_preferred_candidate_route(self):
        balanced = compare_route_qubo_to_classical(ObjectiveWeights())
        carbon_priority = compare_route_qubo_to_classical(
            ObjectiveWeights(cost=0, delivery_time=0, carbon=100, resilience=0)
        )
        self.assertNotEqual(
            balanced.exact_result.decoded_solution["EXP-407"],
            carbon_priority.exact_result.decoded_solution["EXP-407"],
        )
        self.assertTrue(balanced.same_objective)
        self.assertTrue(carbon_priority.same_objective)

    def test_disrupted_candidates_and_shared_capacity_are_used(self):
        self.assertEqual(self.formulation.scenario, ROUTE_QUBO_DEMO_SCENARIO)
        self.assertEqual(
            self.formulation.effective_capacities["road-shanghai-port"], 3
        )
        self.assertTrue(
            any(
                encoding.link_id == "road-shanghai-port"
                for encoding in self.formulation.capacity_encodings
            )
        )
        self.assertTrue(
            any(
                len(route.modes) > 1
                for routes in self.formulation.candidates.values()
                for route in routes
            )
        )

    def test_invalid_formulation_arguments_and_variable_limit(self):
        with self.assertRaisesRegex(ValueError, "exactly one route sequence"):
            formulate_route_assignment_qubo(
                global_demo_network(),
                self.formulation.profiles,
                {"EXP-104": self.formulation.candidates["EXP-104"]},
                ObjectiveWeights(),
                self.formulation.normalization_references,
                self.formulation.scenario,
            )
        # The production demo builder explicitly chooses 3 candidates per shipment;
        # the supported limit is checked by the formulation itself.
        self.assertEqual(self.formulation.variable_count, 8)

    def test_exact_solver_reports_infeasible_restricted_candidate_problem(self):
        restricted = {
            shipment_id: (routes[0],)
            for shipment_id, routes in self.formulation.candidates.items()
        }
        formulation = formulate_route_assignment_qubo(
            global_demo_network(),
            self.formulation.profiles,
            restricted,
            self.formulation.weights,
            self.formulation.normalization_references,
            self.formulation.scenario,
        )
        result = ExactQUBOSolver().solve(
            formulation.solver_request(ProblemRepresentation.QUBO)
        )
        self.assertFalse(result.feasible)
        self.assertIsNone(result.decoded_solution)
        self.assertTrue(result.feasibility_details)

    def test_oversized_generated_candidate_set_is_rejected_not_truncated(self):
        profiles = self.formulation.profiles
        candidates = {
            profile.request.id: generate_candidate_routes(
                self.formulation.network,
                profile.request,
                self.formulation.scenario,
                max_routes=8,
            )
            for profile in profiles
        }
        with self.assertRaisesRegex(UnsupportedRouteQUBOError, "requires .* binary variables"):
            formulate_route_assignment_qubo(
                self.formulation.network,
                profiles,
                candidates,
                self.formulation.weights,
                self.formulation.normalization_references,
                self.formulation.scenario,
            )

    @unittest.skipUnless(QulacsBackend.is_available(), "optional Qulacs SDK unavailable")
    def test_qulacs_qaoa_executes_route_qubo_and_reconciles_original_energy(self):
        result = QulacsQAOASolver(
            QAOAConfig(depth=1, max_iterations=1, shots=16, random_seed=2026)
        ).solve(self.formulation.solver_request(ProblemRepresentation.ISING))
        self.assertEqual(result.status, ExecutionStatus.COMPLETED)
        self.assertIsNotNone(result.best_binary_assignment)
        evaluation = self.formulation.evaluate_assignment(result.best_binary_assignment)
        self.assertEqual(evaluation.full_penalized_energy, result.full_energy)
        self.assertEqual(evaluation.feasibility.feasible, result.feasible)

    @unittest.skipUnless(QiskitBackend.is_available(), "optional Qiskit SDK unavailable")
    def test_qiskit_qaoa_executes_route_qubo_and_reconciles_original_energy(self):
        result = QiskitQAOASolver(
            QAOAConfig(depth=1, max_iterations=1, shots=16, random_seed=2026)
        ).solve(self.formulation.solver_request(ProblemRepresentation.ISING))
        self.assertEqual(result.status, ExecutionStatus.COMPLETED)
        self.assertIsNotNone(result.best_binary_assignment)
        evaluation = self.formulation.evaluate_assignment(result.best_binary_assignment)
        self.assertEqual(evaluation.full_penalized_energy, result.full_energy)
        self.assertEqual(evaluation.feasibility.feasible, result.feasible)
