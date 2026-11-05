# CVRP benchmark suite

Run the reproducible synthetic suite from the repository root:

```sh
PYTHONPATH=src python3 examples/benchmark_cvrp.py
```

The default suite has 5-, 7-, and 9-customer Euclidean instances generated
from a fixed seed. It reports nearest-neighbour, nearest-neighbour + 2-opt, and
exact routes, total distance, feasibility, vehicles used, elapsed time, and
optimality gap against the exact result.

`ExactCVRPSolver` is a reference solver, not a scalable production solver. It
uses subset dynamic programming and accepts at most 10 customers. Runtime and
memory grow exponentially. Synthetic distances are generated from coordinates
and are not map-provider or road-network distances. The nearest-neighbour and
2-opt results are heuristic and are not guaranteed globally optimal.

For suite-generated reports, the benchmark records the per-instance seed and
the depot, demands, capacities, and distance matrix. Failed nearest-neighbour
construction is recorded as `construction_failed` with no route distance or
gap and unknown feasibility; the exact solver still runs. `problem_infeasible`
is reserved for infeasibility established by the exact solver.

Integer and rational distances are summed exactly. Each input Python float is
treated as its exact stored IEEE-754 binary rational value, and route totals
are compared without intermediate float rounding. Demands and capacities use
the same represented-value convention for feasibility. Benchmark timers cover each
method invocation plus common route validation and scoring; they are single
wall-clock observations, not statistically reliable timing claims.
