# Quantum experiment readiness and future Fujitsu comparison

## Validated QSupply baseline

QSupply currently has a backend-neutral `SolverRequest`/sampling contract,
QUBO-to-Ising conversion, exact QUBO enumeration (up to 12 variables), the
multimodal route-assignment QUBO, independent assignment feasibility checks,
and local Qiskit and Qulacs QAOA simulator adapters. The adapters have passed
SDK-enabled tests using the repository-supported Qiskit 2.6.x and Qulacs
0.6.x lines. These are classical local simulations, not quantum hardware.

`qsupply.network.route_qubo_experiments` reuses the existing route model and
quantum benchmark rather than introducing a second solver. It produces frozen
per-run experiment configurations, a content fingerprint of the generated
finite problem, validated exact/classical/QAOA records, and JSON/CSV exports.
Unavailable selected backends remain unavailable; the harness does not choose
a substitute. Requested explicit seeds are recorded per QAOA run, without
assuming every backend applies a seed identically.

## Reproduce the synthetic suite

The presets use deterministic synthetic shipment/network records and fixed
baseline normalization references. They include 8, 10, 11 and 12 total QUBO
variables (decision plus slack bits), with balanced and carbon-priority
weights. Each run stores the shipment set, candidate-generation cap and counts,
scenario, weights, penalty rule and value, offset, backend, QAOA settings,
seed, package versions and a SHA-256 problem fingerprint. Exact results apply
to the generated finite candidate routes only, not all possible network paths.

Use the already isolated environment when available. A fresh environment can
be created outside the repository using the checked-in optional constraints:

```sh
python3 -m venv /tmp/qsupply-experiments
/tmp/qsupply-experiments/bin/python -m pip install -r requirements-qiskit.txt -r requirements-quantum.txt
PYTHONPATH=src /tmp/qsupply-experiments/bin/python examples/benchmark_route_qubo.py
```

The default command runs the 8-variable case with three explicit seeds,
balanced and carbon-priority profiles, QAOA depth 1, two optimizer iterations,
64 shots, and both selected backends. Use `--all-sizes` to run the 8/10/11/12
presets. To write reproducible exports into a new directory:

```sh
PYTHONPATH=src /tmp/qsupply-experiments/bin/python examples/benchmark_route_qubo.py --all-sizes --output-dir /tmp/qsupply-experiment-2026-01
```

Exports are `manifest.json`, `runs.json`, and `summary.csv`. Existing export
files are not overwritten by default. Select backends explicitly with
`--backend qiskit --backend qulacs`; if a selected dependency is unavailable,
the run rows are marked unavailable and the other requested methods continue.
The manifest includes detected versions; absent SDK versions are `null`.

## Comparison methodology

All methods consume the same fixed candidate routes, objective weights,
baseline normalization references, capacity/disruption constraints and
independent feasibility validator. The exact solver reports the penalized
QUBO minimum separately from the best feasible business objective. The
classical `assign_routes` result is encoded back into the same QUBO register.
For every returned assignment, QSupply independently recomputes QUBO energy,
Ising energy and the separately stored offset, then validates route selection,
link loads and route availability before reporting a business objective.
Infeasible plans have no business objective or optimal-feasible gap.

Repeated QAOA runs preserve individual results and use the existing benchmark
statistics, including feasibility and optimal-feasible success rates where
seed application and a feasible reference make those quantities meaningful.
Execution timings use each adapter's documented scope. They are observations
from the current local machine; they are not statistically reliable speed
claims. No speedup or quantum advantage is inferred.

## Future QARP comparison methodology

Once an authorized, documented QARP interface has been inspected and tested,
compare it against these fixed problem fingerprints and the same objective,
constraints, candidate routes, validation, seeds where supported, and reporting
definitions. Capture backend identity/version, execution mode, shots, effective
seed behavior, submission/queue/execution/retrieval times only when the backend
actually reports or measures them, raw sample counts when export is permitted,
and QSupply-recomputed energies and feasibility. Report missing measurements as
unavailable. Keep simulator, remote service and hardware timing scopes
separate. Preserve individual trials and disclose any backend-specific
sampling or precision differences.

## Information needed before any QARP adapter

The following are not verified and must be established from authorized
Fujitsu documentation or an approved environment before implementation:

- Supported package/API and pinned compatible versions.
- Supported problem representations, coefficient types and variable limits.
- Whether QARP accepts QUBO, Ising, circuits, or another representation.
- Submission, authentication, execution and result-retrieval workflow.
- Whether execution is local, remote, hardware-backed, synchronous, or job-based.
- Supported shots, seeds, parameter ranges, constraints and result formats.
- FX700 connectivity, network/static-IP prerequisites and permitted access.
- Timing fields, reproducibility guarantees, data retention and export rules.
- Challenge rules governing software, data, experiment artifacts and publication.

No QARP backend is implemented or registered. This repository contains no
QARP credentials, private keys, confidential test procedures or Fujitsu
proprietary materials. No FX700 connection is attempted by this readiness
work.

## Current limitations

The datasets are illustrative synthetic cases. Candidate route generation is
bounded, exact enumeration is limited to 12 total variables, and QAOA runs use
local classical state-vector simulation. Network/business metrics originate
from existing floating-point synthetic route data even though QUBO arithmetic
preserves exact stored rational representations. The benchmark therefore
validates formulation and repeatable software behavior, not deployment
performance, operational forecast quality or quantum advantage.
