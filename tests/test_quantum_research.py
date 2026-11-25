"""Check the published snapshot against the catalogue, route model and raw trials."""
import csv
import json
import unittest
from fractions import Fraction
from pathlib import Path

from examples.quantum_research import PROFILES, TRIAL_SEEDS, catalogue
from qsupply.network.route_qubo_experiments import _problem


class TestSavedResearch(unittest.TestCase):
    def test_archived_cases_and_energies(self):
        root = Path(__file__).resolve().parents[1] / "benchmarks/quantum"
        cases = json.loads((root / "study.json").read_text())["cases"]
        runs = json.loads((root / "runs.json").read_text())
        with (root / "summary.csv").open() as stream:
            summaries = list(csv.DictReader(stream))
        specs = list(catalogue())
        self.assertEqual(len(cases), 21)
        self.assertEqual(len({frozenset(s.shipment_ids) for s, _, _ in specs}), len(cases))
        self.assertEqual(len(summaries), sum(len(c["methods"]) for c in cases))
        for (spec, profile, selected), case in zip(specs, cases, strict=True):
            self.assertEqual(case["id"], spec.problem_id)
            records = [r for r in runs if r["instance"] == spec.problem_id]
            if spec.problem_id == "size-control":
                self.assertGreater(case["variables"], 12)
                exact = next(r for r in records if r["solver"] == "exact-qubo")
                self.assertEqual(exact["status"], "unavailable")
                self.assertIsNone(case["exact"])
                continue
            model, _ = _problem(spec, PROFILES[profile])
            for r in records:
                if r["assignment"] is None:
                    self.assertNotEqual(r["status"], "completed")
                    continue
                value = model.evaluate_assignment(r["assignment"])
                self.assertEqual(value.full_penalized_energy, Fraction(r["ising_energy"]))
                self.assertEqual(value.feasibility.feasible, r["feasible"])
                if r["feasible"]:
                    self.assertEqual(value.business_metrics.weighted_objective, Fraction(r["business_objective"]))
                else:
                    self.assertIsNone(r["optimal_feasible_gap_percent"])
            if selected:
                for solver in ("qiskit", "qulacs"):
                    trials = [r for r in records if r["solver"] == solver]
                    self.assertEqual([r["configuration"]["random_seed"] for r in trials], list(TRIAL_SEEDS))
                    summary = next(m for m in case["methods"] if m["method"] == solver)
                    self.assertEqual(summary["feasible"], sum(r["feasible"] is True for r in trials))
                    hits = sum(r["business_objective"] == case["exact"] for r in trials if r["feasible"])
                    self.assertEqual(summary["optimal_rate"], hits / len(trials))
