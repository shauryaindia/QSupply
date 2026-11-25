"""Generate the Milestone 7B synthetic route study and its dashboard snapshot."""
import argparse
import csv
import json
from collections import Counter
from dataclasses import asdict
from fractions import Fraction
from itertools import combinations
from pathlib import Path
from random import Random
from statistics import mean
from time import perf_counter

from qsupply.network import ObjectiveWeights, UnsupportedRouteQUBOError, assign_routes
from qsupply.network.global_demo import global_demo_network, global_demo_shipments
from qsupply.network.route_qubo_experiments import (
    SYNTHETIC_ROUTE_EXPERIMENTS, RouteExperimentSpec, prepare_route_candidates,
    run_route_experiments,
)

GENERATION_SEED = 7102
TRIAL_SEEDS = (11, 22, 33, 44, 55)
PROFILES = {
    "balanced": ObjectiveWeights(),
    "carbon": ObjectiveWeights(0, 0, 100, 0),
    "time": ObjectiveWeights(0, 100, 0, 0),
}


def catalogue():
    """Four preselected quantum cases, sixteen unique shipment sets and a size control."""
    for spec, profile in zip(SYNTHETIC_ROUTE_EXPERIMENTS, ("balanced", "carbon", "balanced", "time"), strict=True):
        yield spec, profile, True
    rng = Random(GENERATION_SEED)
    ids = sorted(p.request.id for p in global_demo_shipments())
    used = {tuple(sorted(spec.shipment_ids)) for spec in SYNTHETIC_ROUTE_EXPERIMENTS}
    pool = [group for n in (1, 2, 3) for group in combinations(ids, n) if group not in used]
    for i, group in enumerate(rng.sample(pool, 16)):
        scenario = (None, "synthetic-singapore-customs-delay", "synthetic-suez-capacity-restriction",
                    "synthetic-china-us-port-closure")[i % 4]
        yield RouteExperimentSpec(f"portfolio-{i+1:02}", group, 2 + i % 2, scenario), rng.choice(tuple(PROFILES)), False
    yield RouteExperimentSpec("size-control", tuple(ids), 3, None), "balanced", False


def summarize(method, rows, reference):
    completed = [r for r in rows if r["status"] == "completed"]
    feasible = [r for r in completed if r["feasible"] is True]
    objectives = [Fraction(r["business_objective"]) for r in feasible]
    gaps = [r["optimal_feasible_gap_percent"] for r in feasible if r["optimal_feasible_gap_percent"] is not None]
    times = [r["execution_time_seconds"] for r in rows if r["execution_time_seconds"] is not None]
    seeded = all((r["backend_metadata"] or {}).get("seed_applied") is True for r in rows)
    evaluable = [r for r in completed if r["feasible"] is not None]
    metadata = [r["backend_metadata"] or {} for r in completed]
    depths = sorted({m["circuit_depth"] for m in metadata if m.get("circuit_depth") is not None})
    evaluations = [m["optimizer_evaluations"] for m in metadata if m.get("optimizer_evaluations") is not None]
    return dict(method=method, outcomes=dict(Counter(r["status"] for r in rows)), circuit_depths=depths, optimizer_evaluations=sum(evaluations) if evaluations else None, trials=len(rows), completed=len(completed), feasible=len(feasible),
                feasibility_rate=len(feasible)/len(evaluable) if evaluable else None,
                optimal_rate=(sum(v == reference for v in objectives)/len(rows)
                              if seeded and reference is not None else None),
                best_objective=float(min(objectives)) if objectives else None,
                mean_gap_percent=mean(gaps) if gaps else None,
                mean_seconds=mean(times) if times else None)


def run_study():
    cases, trials = [], []
    for spec, profile, selected in catalogue():
        weights = PROFILES[profile]
        case = dict(id=spec.problem_id, shipments=spec.shipment_ids, route_cap=spec.max_routes_per_shipment,
                    scenario=spec.scenario_id, profile=profile, weights=asdict(weights), selected=selected)
        try:
            report = run_route_experiments(specs=(spec,), weights_by_profile={profile: weights},
                backends=("qiskit", "qulacs") if selected else (), seeds=TRIAL_SEEDS)
        except UnsupportedRouteQUBOError as error:
            profiles, scenario, comparison = prepare_route_candidates(spec, weights)
            started = perf_counter()
            plan = assign_routes(global_demo_network(), profiles, comparison.recovery_candidates,
                                 weights, comparison.normalization_references, scenario)
            elapsed = perf_counter() - started
            rows = [dict(solver="classical-assignment", status="completed" if plan else "infeasible",
                         feasible=plan is not None, execution_time_seconds=elapsed,
                         business_objective=str(plan.metrics.weighted_objective) if plan else None,
                         selected_routes={k: v.id for k,v in plan.routes.items()} if plan else None,
                         optimal_feasible_gap_percent=None, backend_metadata=None),
                    dict(solver="exact-qubo", status="unavailable", feasible=None, execution_time_seconds=None,
                         business_objective=None, optimal_feasible_gap_percent=None, backend_metadata=None)]
            ref = None
            case.update(variables=error.variable_count, candidates=sum(map(len, comparison.recovery_candidates.values())),
                        exact=None, reason=str(error))
        else:
            instance = report.manifest["instances"][0]
            rows = [r.to_dict() for r in report.runs]
            optimum = instance["exact_best_feasible_objective"]
            ref = Fraction(optimum) if optimum is not None else None
            case.update(variables=instance["variables"], candidates=instance["candidate_routes"],
                        exact=str(ref) if ref is not None else None, fingerprint=instance["fingerprint"],
                        reason=None if ref is not None else "No feasible plan over these candidates.")
        case["methods"] = [summarize(m, [r for r in rows if r["solver"] == m], ref)
                           for m in dict.fromkeys(r["solver"] for r in rows)]
        trials.extend(dict(instance=spec.problem_id, **r) for r in rows)
        cases.append(case)
    return dict(software_versions=next(r["configuration"]["software_versions"] for r in trials if "configuration" in r),
                generation_seed=GENERATION_SEED, seeds=TRIAL_SEEDS, depth=1, iterations=2,
                optimizer="spsa", shots=64, cases=cases), trials


def display(value):
    return "—" if value is None else f"{value:.4g}"


def write_report(directory, study, trials):
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in (("study", study), ("runs", trials)):
        (directory / (name + ".json")).write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    lines = ["# Synthetic multimodal route study", "",
             "Each shipment selects one generated route. The objective is the priority-weighted sum of baseline-normalized freight and delay cost, time, carbon and disruption exposure.",
             "", "For route bits x, add A(Σx−1)² per shipment and A(load + slack − capacity)² per binding link. A is one plus the sum of maximum per-shipment route scores. Substituting x=(1−z)/2 gives the Ising Hamiltonian. The constant is restored when scoring samples.",
             "", "Portfolio generation seed 7102. Four preset sizes were selected before sampling. Both local simulators used depth 1, SPSA, two iterations, 64 shots per evaluation and seeds 11, 22, 33, 44, 55. Each method used the same candidates, weights and baseline normalization within its case.",
             "", "For ordered-pair Q, write aᵢⱼ=Qᵢⱼ+Qⱼᵢ for i<j. In H=C+Σhᵢzᵢ+ΣJᵢⱼzᵢzⱼ, Jᵢⱼ=aᵢⱼ/4, hᵢ=−Qᵢᵢ/2−Σⱼ≠ᵢaᵢⱼ/4 (using symmetric pair totals), and C=offset+ΣQᵢᵢ/2+Σᵢ<ⱼaᵢⱼ/4.", "", "## Instances", "", "| ID | Shipment IDs | Route cap | Candidates | Bits | Overlay | Weight profile |",
             "|---|---|---:|---:|---:|---|---|"]
    for c in study["cases"]:
        lines.append(f"| {c['id']} | {', '.join(c['shipments'])} | {c['route_cap']} | {c['candidates']} | {c['variables']} | {c['scenario'] or 'Baseline'} | {c['profile']} |")
    lines.extend(["", "Balanced weights are 40/25/20/15 for cost/time/carbon/exposure. Carbon and time profiles give their named metric 100%.",
                  "", "## Measured results", "", "| Instance | Method | Feasible / trials | Optimal rate | Best objective | Mean feasible gap (%) | Mean solver time (s) |",
                  "|---|---|---:|---:|---:|---:|---:|"])
    with (directory / "summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["instance", *study["cases"][0]["methods"][0]], lineterminator="\n")
        writer.writeheader()
        for c in study["cases"]:
            for m in c["methods"]:
                writer.writerow(dict(instance=c["id"], **{k: json.dumps(v) if isinstance(v, (dict, list)) else v for k,v in m.items()}))
                count = f"{m['feasible']}/{m['trials']}" if m["feasibility_rate"] is not None else ", ".join(m["outcomes"])
                lines.append(f"| {c['id']} | {m['method']} | {count} | {display(m['optimal_rate'])} | {display(m['best_objective'])} | {display(m['mean_gap_percent'])} | {display(m['mean_seconds'])} |")
    lines.extend(["", "## Observations", ""])
    for backend in ("qiskit", "qulacs"):
        sampled = [r for r in trials if r["solver"] == backend]
        references = {c["id"]: c["exact"] for c in study["cases"]}
        hits = sum(r["status"] == "completed" and r["feasible"] is True
                   and Fraction(r["business_objective"]) == Fraction(references[r["instance"]])
                   for r in sampled if references[r["instance"]] is not None)
        valid = sum(r["status"] == "completed" and r["feasible"] is True for r in sampled)
        lines.append(f"- {backend.title()} returned {valid} feasible plans across {len(sampled)} requested trials. {hits} matched the exact candidate-set objective.")
    for c in study["cases"]:
        if c["reason"]:
            lines.append(f"- {c['id']}: {c['reason']}")
    versions = study["software_versions"]
    lines.extend(["", "## Simulator execution", "",
                  f"Local Python {versions['python']}, Qiskit {versions['qiskit']} and Qulacs {versions['qulacs']}. Depth below is the native circuit depth before measurement. Evaluations count optimizer sampling calls, excluding the final measurement.",
                  "", "| Case | Simulator | Circuit depth | Optimizer evaluations across trials |", "|---|---|---:|---:|"])
    for case in study["cases"]:
        for method in case["methods"]:
            if method["method"] in ("qiskit", "qulacs"):
                depths = ", ".join(map(str, method["circuit_depths"])) or "—"
                lines.append(f"| {case['id']} | {method['method']} | {depths} | {display(method['optimizer_evaluations'])} |")
    lines.extend(["", "Feasibility counts evaluate the returned minimum-energy sample of each completed trial. Success is the fraction of requested seeded trials with an independently feasible assignment matching the exact business objective. Missing seed confirmation gives an unavailable rate. Objective gaps average only validated feasible outcomes with a nonzero reference. Exact fractions and individual violations are in runs.json.",
                  "", "## Scaling and limitations", "",
                  "Exact enumeration doubles its search space with each additional bit. The size-control case exceeds the 12-bit guard. Its exact reference and gap are unavailable, and its classical objective uses the route planner’s native floating-point score. All other references apply only to generated candidates. Three different objective profiles and different networks of candidates prevent attributing observed changes solely to size.",
                  "", "Solver timings are local observations and exclude candidate generation. Optimizer and sampling times overlap. Native SDK gate depths depend on gate decomposition. Five seeds give success rates in increments of 20 percentage points. A larger paired seed study across matched capacities and objective profiles would improve uncertainty estimates.",
                  "", "Reproduce from the repository root with the supported SDKs installed in an isolated environment: `PYTHONPATH=src python examples/quantum_research.py OUTPUT_DIRECTORY`. The directory receives this report, study.json, runs.json and summary.csv. Machine timings vary."])
    (directory / "report.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    directory = parser.parse_args().directory
    write_report(directory, *run_study())
