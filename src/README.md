# Implemented source modules

The `qsupply` package currently contains a minimal, dependency-free QUBO model.
It stores named binary variables and coefficients keyed by ordered variable
pairs, and evaluates the objective exactly as supplied.

```python
from qsupply import QUBO

model = QUBO(
    variables=("x0", "x1"),
    coefficients={("x0", "x0"): -2, ("x1", "x1"): -3, ("x0", "x1"): 4},
)
print(model.energy({"x0": 1, "x1": 1}))  # -1
```

Assignments must include every declared variable, contain no unknown
variables, and use only 0 or 1. Python booleans are accepted (`False` is 0 and
`True` is 1). Coefficient keys are ordered pairs: supplying `(x0, x1)` and
`(x1, x0)` adds both terms, so equal coefficients of 4 contribute 8 when both
variables are 1. From the repository root, run the tests with
`PYTHONPATH=src python3 -m unittest discover -s tests`.

## Import-export supply-chain QUBO

`ImportExportProblem` describes shipments, candidate transport options,
deadlines, lane usage and lane capacities. `formulate_import_export_qubo`
creates one binary selection variable per shipment-option pair and binary
slack bits per lane. It adds squared penalties for exactly-one selection and
capacity equalities. The resulting `QUBO` preserves ordered-pair semantics;
the formulation stores the expansion's constant offset separately and
`full_energy(assignment)` includes it.

For option (o) of shipment (s), the business coefficient is
`freight + time_weight * delivery_time + delay_rate * max(0, delivery_time - deadline) + carbon_weight * carbon`.
The binary variable `x[s,o]` indicates the selected option. The penalties are
`P * (1 - sum_o x[s,o])**2` and, for each lane, `P * (sum usage[s,o] * x[s,o] + slack - capacity)**2`.
Slack is represented by binary powers of two. `P` is one above the sum of
each shipment's maximum option cost, an upper bound on every feasible
business cost. Since costs are non-negative and lane units are integral, any
violated one-hot or capacity equality adds at least `P`; if a feasible plan
exists, no infeasible assignment can minimize full energy. This guarantee
does not prove the instance is feasible.

`decode` validates a complete binary assignment and requires one selected
option per shipment. `check_feasibility` independently checks those choices
and recomputes lane usage from the original problem data. The business-cost
evaluator is separate from penalty energy. Lane usage and capacity use
integer-scaled units. The model supports discrete shipment-option selection
and shared linear capacities; it does not yet model route sequencing,
continuous quantities, uncertain lead times, inventory balance or disruption
recourse. This is a formulation demonstration, not an optimization solver.
Float cost inputs are interpreted as their exact stored IEEE-754 rational
values during formulation and evaluation.
Run `PYTHONPATH=src python3 examples/import_export_qubo.py` for a 32-assignment
exhaustive example.

## QUBO to Ising conversion

`qubo_to_ising(qubo, offset=...)` converts the existing ordered-pair QUBO to
the canonical Ising energy `C + sum(h[i] * z[i]) + sum(J[i,j] * z[i] * z[j])`.
It uses `z[i] = 1 - 2*x[i]`: binary 0 maps to spin +1 and binary 1 to spin
-1. The QUBO diagonal becomes linear; for each unordered pair in declared
variable order, the converter combines both supplied orientations as
`Q[i,j] + Q[j,i]`. It does not mutate the QUBO.

The `IsingModel` retains the QUBO variable order and exposes a read-only
`variable_indices` mapping from variable name to register index. Its
`energy(spins)` method accepts complete ±1 spin assignments, and
`energy_from_binary(bits)` evaluates the same energy from complete 0/1 bits.
Integer and rational coefficients use exact rational factors during
conversion. For import-export formulations, preserve the separately stored
constant by passing it explicitly:

```python
from qsupply import formulate_import_export_qubo, qubo_to_ising

formulation = formulate_import_export_qubo(problem)
ising = qubo_to_ising(formulation.qubo, offset=formulation.offset)
# ising.energy_from_binary(bits) == formulation.full_energy(bits)
```

This is a mathematical representation only; it does not build a quantum
circuit or connect to a solver backend.

## Common solver contract and exact QUBO reference

The backend-independent execution types are exported from `qsupply`:
`Solver`, `SolverMetadata`, `SolverRequest`, `SolverResult`, and the backend,
representation, and status enums. Backend SDK objects do not appear in this
interface. A solver reports both its candidate energy and QSupply's
independently recalculated QUBO/full energy. The result also keeps Ising
energy, optional feasibility, decoded plan, and business objective separate.

`ExactQUBOSolver` exhaustively evaluates every binary assignment through
`QUBO.energy`. It has a configurable variable limit, defaulting to 12
variables (4,096 assignments). This conservative default reflects the
exponential candidate count and the repeated coefficient evaluation for each
candidate; callers can explicitly raise it when that cost is acceptable.
Dense QUBOs require additional work per assignment. It is a deterministic
small-instance classical reference, not a quantum solver or a scalable optimizer. Equal
energies resolve to the lexicographically first bit tuple in declared variable
order. Integer and rational energies are not converted to floats. The
separately supplied constant offset is included in `full_energy` and the
converted `ising_energy`.

```python
from qsupply import ExactQUBOSolver, QUBO, SolverRequest

problem = QUBO(("choose_a", "choose_b"), {
    ("choose_a", "choose_a"): -2,
    ("choose_b", "choose_b"): -3,
    ("choose_a", "choose_b"): 4,
})
result = ExactQUBOSolver().solve(SolverRequest(problem, constant_offset=10))
print(dict(result.best_binary_assignment))
print(result.qubo_energy, result.full_energy, result.ising_energy)
```

An optional domain validator receives the full assignment. Decoding and a
business-objective callback run only if it reports feasibility. For
import-export formulations, pass the existing independent methods, for
example `validator=formulation.check_feasibility` and
`decoder=formulation.decode`; this keeps business feasibility distinct from
minimum QUBO energy. `benchmark_solvers(request, solvers)` captures comparable
problem size, solver identity, energy, feasibility, candidate count, elapsed
time, configuration and seed. Current records are single-run observations,
not statistical performance claims. The API run-history service remains
CVRP-specific and is not changed by this core solver milestone.

## CVRP route data model

`CVRPProblem` represents one depot, customer delivery demands, vehicle-specific
capacities, and a complete directed distance matrix. Provide each vehicle's
route as an ordered sequence that includes the depot at both ends. The model
checks that every customer appears exactly once, all references are valid, and
each vehicle stays within capacity. `transportation_cost(routes)` validates
the routes and sums the distances of their traveled arcs.

Run [`examples/cvrp_synthetic.py`](../examples/cvrp_synthetic.py) with
`PYTHONPATH=src python3` to see a five-customer, two-vehicle example. Its
Euclidean distances are synthetic and do not come from a mapping service.
`NearestNeighborTwoOptSolver` adds a deterministic capacity-constrained
nearest-neighbour construction followed by best-improvement 2-opt within each
route. The result contains routes, the initial nearest-neighbour distance, the
post-2-opt distance, and percentage improvement. This is a heuristic with no
global-optimality guarantee. Greedy assignment can fail to find a solution for
some feasible CVRPs; such cases raise a clear construction error. No QAOA,
quantum advantage, or real-world map integration is implemented.

## CVRP benchmarking and exact reference

`ExactCVRPSolver` supplies a minimum-distance reference for supported small
instances. It uses Held–Karp subset dynamic programming for route costs
and a capacity-aware subset partition across vehicles. The hard limit is
`MAX_EXACT_CUSTOMERS = 10`; computation grows exponentially (route costs use
`O(n² 2ⁿ)` time and subset assignment up to `O(V 3ⁿ)`), so this is not intended
for operational-size routing. Integer and rational distances are compared and
reported exactly. Each Python float is interpreted as its exact stored
IEEE-754 binary rational value; route sums use rational arithmetic with no
rounding tolerance. The same exact-represented-value convention applies to
demands and capacities during feasibility checks. There is no tolerance around
capacity boundaries. This can return a `Fraction` distance for float inputs.

`generate_synthetic_cvrp` and `synthetic_benchmark_suite` create reproducible
Euclidean instances using a standard-library seeded random generator. The
default suite contains 5, 7, and 9 customers. `benchmark_suite` compares
nearest-neighbour, nearest-neighbour + 2-opt, and exact routes. It records
distance, feasibility, vehicles used, elapsed wall-clock time, and heuristic
optimality gap against the exact distance. Heuristic construction failures are
reported with `status="construction_failed"`, unknown feasibility, and no
distance or gap; this does not prove the CVRP infeasible. Exact infeasibility
is reported separately. Benchmark results include the seed when generated by
the suite and a copy of the instance configuration. Timers include method
execution plus common route validation and exact-rational scoring, but are
single-run observations rather than statistically reliable performance
claims. Synthetic distances are not real-world map data. Run
`PYTHONPATH=src python3 examples/benchmark_cvrp.py`.
