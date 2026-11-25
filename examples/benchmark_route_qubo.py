"""Run a reproducible experiment suite over synthetic route-assignment QUBOs."""

from __future__ import annotations

import argparse
import json

from qsupply.network.route_qubo_experiments import (
    SYNTHETIC_ROUTE_EXPERIMENTS,
    export_experiment_report,
    run_route_experiments,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-sizes", action="store_true", help="run the 8, 10, 11 and 12 variable presets")
    parser.add_argument("--output-dir", help="write manifest.json, runs.json and summary.csv to a new directory")
    parser.add_argument("--seed", action="append", type=int, dest="seeds", help="explicit seed; repeat at least three times for three trials")
    parser.add_argument("--backend", action="append", dest="backends", choices=("qiskit", "qulacs"),
                        help="backend selection; repeat to choose both (unselected backends are not substituted)")
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--shots", type=int, default=64)
    args = parser.parse_args()
    report = run_route_experiments(
        specs=SYNTHETIC_ROUTE_EXPERIMENTS if args.all_sizes else SYNTHETIC_ROUTE_EXPERIMENTS[:1],
        seeds=tuple(args.seeds or (11, 22, 33)),
        backends=tuple(args.backends or ("qiskit", "qulacs")),
        iterations=args.iterations,
        shots=args.shots,
    )
    if args.output_dir:
        paths = export_experiment_report(report, args.output_dir)
        print(json.dumps({"exports": [str(path) for path in paths],
                          "instance_count": len(report.manifest["instances"]),
                          "run_count": len(report.runs)}, indent=2))
    else:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
