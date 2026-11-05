import itertools
import unittest
from fractions import Fraction

from qsupply import (
    ImportExportProblem,
    Shipment,
    TransportOption,
    evaluate_business_objective,
    formulate_import_export_qubo,
    synthetic_import_export_problem,
)


class TestImportExportFormulation(unittest.TestCase):
    def setUp(self):
        self.problem = synthetic_import_export_problem()
        self.formulation = formulate_import_export_qubo(self.problem)

    def assignment_for(self, selections, slack=0):
        assignment = {variable: 0 for variable in self.formulation.qubo.variables}
        for shipment, option in selections.items():
            variable = self.formulation.decision_variables[(shipment, option)]
            assignment[variable] = 1
        for variable, weight in self.formulation.slack_variables["L1"]:
            if slack & weight:
                assignment[variable] = 1
        return assignment

    def test_synthetic_problem_has_expected_option_costs(self):
        self.assertEqual(
            evaluate_business_objective(self.problem, {"S1": "B", "S2": "A"}), 17
        )
        self.assertEqual(
            evaluate_business_objective(self.problem, {"S1": "A", "S2": "B"}), 18
        )

    def test_variable_mapping_and_exact_qubo_coefficients(self):
        self.assertEqual(
            dict(self.formulation.decision_variables),
            {
                ("S1", "A"): "select_s0_o0",
                ("S1", "B"): "select_s0_o1",
                ("S2", "A"): "select_s1_o0",
                ("S2", "B"): "select_s1_o1",
            },
        )
        self.assertEqual(self.formulation.slack_variables["L1"], (("slack_l0_b0", 1),))
        self.assertEqual(self.formulation.penalty, 20)
        self.assertEqual(self.formulation.offset, 60)
        self.assertEqual(
            dict(self.formulation.qubo.coefficients),
            {
                ("select_s0_o0", "select_s0_o0"): -32,
                ("select_s0_o1", "select_s0_o1"): -11,
                ("select_s1_o0", "select_s1_o0"): -32,
                ("select_s1_o1", "select_s1_o1"): -10,
                ("select_s0_o0", "select_s0_o1"): 40,
                ("select_s1_o0", "select_s1_o1"): 40,
                ("select_s0_o0", "select_s1_o0"): 40,
                ("select_s0_o0", "slack_l0_b0"): 40,
                ("select_s1_o0", "slack_l0_b0"): 40,
                ("slack_l0_b0", "slack_l0_b0"): -20,
            },
        )

    def test_optimal_plan_energy_and_separate_evaluation_components(self):
        assignment = self.assignment_for({"S1": "B", "S2": "A"})
        plan = self.formulation.decode(assignment)
        evaluation = self.formulation.evaluate(assignment)
        self.assertEqual(dict(plan), {"S1": "B", "S2": "A"})
        self.assertEqual(evaluation.business_cost, 17)
        self.assertEqual(evaluation.penalty_contribution, 0)
        self.assertEqual(evaluation.qubo_offset, 60)
        self.assertEqual(evaluation.qubo_energy, -43)
        self.assertEqual(evaluation.full_penalized_energy, 17)
        self.assertEqual(self.formulation.full_energy(assignment), 17)

    def test_independent_feasibility_checks_lane_usage(self):
        feasible = self.assignment_for({"S1": "B", "S2": "A"})
        report = self.formulation.check_feasibility(feasible)
        self.assertTrue(report.feasible)
        self.assertEqual(dict(report.lane_usage), {"L1": 1})

        without_slack = {
            variable: value
            for variable, value in feasible.items()
            if variable not in {name for name, _ in self.formulation.slack_variables["L1"]}
        }
        self.assertTrue(self.formulation.check_feasibility(without_slack).feasible)

        over_capacity = self.assignment_for({"S1": "A", "S2": "A"})
        report = self.formulation.check_feasibility(over_capacity)
        self.assertFalse(report.feasible)
        self.assertIn("lane 'L1' usage 2 exceeds capacity 1", report.violations)

    def test_feasibility_checker_checks_one_hot_directly(self):
        assignment = self.assignment_for({"S1": "A", "S2": "A"})
        assignment[self.formulation.decision_variables[("S1", "B")]] = 1
        report = self.formulation.check_feasibility(assignment)
        self.assertFalse(report.feasible)
        self.assertTrue(
            any(
                "S1" in violation and "exactly one" in violation
                for violation in report.violations
            )
        )

        missing_choice = self.assignment_for({"S2": "A"})
        report = self.formulation.check_feasibility(missing_choice)
        self.assertFalse(report.feasible)
        self.assertTrue(
            any(
                "S1" in violation and "selected 0" in violation
                for violation in report.violations
            )
        )

    def test_boolean_assignment_values_are_accepted(self):
        assignment = self.assignment_for({"S1": "B", "S2": "A"})
        boolean_assignment = {variable: bool(value) for variable, value in assignment.items()}
        self.assertEqual(
            dict(self.formulation.decode(boolean_assignment)), {"S1": "B", "S2": "A"}
        )
        self.assertTrue(self.formulation.check_feasibility(boolean_assignment).feasible)

    def test_decode_rejects_missing_extra_nonbinary_and_non_one_hot_assignments(self):
        complete = self.assignment_for({"S1": "B", "S2": "A"})
        missing = dict(complete)
        missing.pop(next(iter(missing)))
        with self.assertRaisesRegex(ValueError, "missing variables"):
            self.formulation.decode(missing)
        extra = dict(complete, extra=1)
        with self.assertRaisesRegex(ValueError, "unknown variables"):
            self.formulation.decode(extra)
        nonbinary = dict(complete)
        nonbinary[next(iter(nonbinary))] = 0.5
        with self.assertRaisesRegex(ValueError, "must be 0 or 1"):
            self.formulation.decode(nonbinary)
        not_one_hot = dict(complete)
        not_one_hot[self.formulation.decision_variables[("S1", "B")]] = 0
        with self.assertRaisesRegex(ValueError, "exactly one option"):
            self.formulation.decode(not_one_hot)

    def test_exhaustive_32_assignments_match_independent_direct_formula(self):
        variables = self.formulation.qubo.variables
        for bits in itertools.product((0, 1), repeat=len(variables)):
            assignment = dict(zip(variables, bits))
            business_cost = 0
            for shipment in self.problem.shipments:
                for option in shipment.options:
                    selected = assignment[
                        self.formulation.decision_variables[(shipment.name, option.name)]
                    ]
                    lateness = max(0, option.delivery_time - shipment.deadline)
                    business_cost += selected * (
                        option.freight_cost
                        + option.delivery_time
                        + shipment.delay_penalty_per_unit * lateness
                        + option.carbon_impact
                    )

            direct_penalty = 0
            for shipment in self.problem.shipments:
                count = sum(
                    assignment[self.formulation.decision_variables[(shipment.name, option.name)]]
                    for option in shipment.options
                )
                direct_penalty += self.formulation.penalty * (1 - count) ** 2
            lane_use = sum(
                option.lane_usage.get("L1", 0)
                * assignment[self.formulation.decision_variables[(shipment.name, option.name)]]
                for shipment in self.problem.shipments
                for option in shipment.options
            )
            slack = assignment["slack_l0_b0"]
            direct_penalty += self.formulation.penalty * (lane_use + slack - 1) ** 2

            self.assertEqual(
                self.formulation.business_cost_of_assignment(assignment), business_cost
            )
            self.assertEqual(self.formulation.penalty_contribution(assignment), direct_penalty)
            self.assertEqual(
                self.formulation.offset + self.formulation.qubo.energy(assignment),
                business_cost + direct_penalty,
            )

    def test_infeasible_energy_bound_includes_constant_offset(self):
        feasible_energies = []
        infeasible_energies = []
        for bits in itertools.product((0, 1), repeat=len(self.formulation.qubo.variables)):
            assignment = dict(zip(self.formulation.qubo.variables, bits))
            full_energy = self.formulation.full_energy(assignment)
            if self.formulation.check_feasibility(assignment).feasible:
                feasible_energies.append(full_energy)
            else:
                infeasible_energies.append(full_energy)
        self.assertTrue(feasible_energies)
        self.assertGreater(min(infeasible_energies), min(feasible_energies))
        self.assertGreaterEqual(min(infeasible_energies), 20)

    def test_exhaustive_minimum_is_documented_optimum(self):
        feasible = []
        for bits in itertools.product((0, 1), repeat=len(self.formulation.qubo.variables)):
            assignment = dict(zip(self.formulation.qubo.variables, bits))
            if self.formulation.check_feasibility(assignment).feasible:
                feasible.append((self.formulation.full_energy(assignment), assignment))
        energy, assignment = min(feasible, key=lambda item: item[0])
        self.assertEqual(energy, 17)
        self.assertEqual(dict(self.formulation.decode(assignment)), {"S1": "B", "S2": "A"})

    def test_problem_rejects_unknown_lanes_and_duplicate_names(self):
        with self.assertRaisesRegex(ValueError, "unknown lanes"):
            ImportExportProblem(
                shipments=(
                    Shipment("S", 1, 1, (TransportOption("A", 1, 1, 1, {"bad": 1}),)),
                ),
                lane_capacities={"L1": 1},
            )
        with self.assertRaisesRegex(ValueError, "shipment names must be unique"):
            ImportExportProblem(
                shipments=(
                    Shipment("S", 1, 1, (TransportOption("A", 1, 1, 1, {}),)),
                    Shipment("S", 1, 1, (TransportOption("B", 1, 1, 1, {}),)),
                ),
                lane_capacities={"L1": 1},
            )

    def test_business_objective_rejects_incomplete_or_unknown_plan(self):
        with self.assertRaisesRegex(ValueError, "missing shipments"):
            evaluate_business_objective(self.problem, {"S1": "A"})
        with self.assertRaisesRegex(ValueError, "unknown option"):
            evaluate_business_objective(self.problem, {"S1": "bad", "S2": "A"})

    def test_float_costs_are_converted_to_exact_stored_rationals(self):
        problem = ImportExportProblem(
            shipments=(
                Shipment(
                    "S",
                    1.0,
                    2.0,
                    (TransportOption("A", 0.1, 0.2, 0.4, {}),),
                ),
            ),
            lane_capacities={"L": 1},
        )
        formulation = formulate_import_export_qubo(problem)
        assignment = {variable: 0 for variable in formulation.qubo.variables}
        assignment[formulation.decision_variables[("S", "A")]] = 1
        assignment.update(
            {
                variable: 1
                for variable, weight in formulation.slack_variables["L"]
                if weight == 1
            }
        )
        expected = Fraction(0.1) + Fraction(0.2) + Fraction(0.4)
        self.assertEqual(evaluate_business_objective(problem, {"S": "A"}), expected)
        self.assertEqual(formulation.full_energy(assignment), expected)


if __name__ == "__main__":
    unittest.main()
