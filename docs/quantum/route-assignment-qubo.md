# Multimodal route-assignment QUBO bridge

## Scope

`qsupply.network.route_qubo` converts a finite, already generated set of
multimodal routes into an ordinary QSupply `QUBO`. It does not generate paths
or change `assign_routes`; it consumes those existing candidate routes. The
first API and runnable example use two labelled synthetic shipments, three
recovery candidates per shipment, and a synthetic capacity reduction on
Shanghai port-road access. The 12-variable cap includes route-choice and
capacity-slack bits, matching the current exact QUBO and QAOA limits.

## Objective

For shipment `s` and candidate route `r`, `x[s,r]` is 1 when that route is
selected. Its QBO score follows the global planner's existing weighted,
baseline-normalized semantics:

```text
c[s,r] = priority[s] * Σ_k (weight[k] / 100)
                         * metric[k,s,r] / reference[k]
```

The cost metric is route freight plus the existing modeled lateness penalty;
the other metrics are delivery time, carbon and resilience exposure. The
normalization references come from the undisturbed baseline candidate set and
remain fixed for the disruption comparison. This avoids changing the scale
between baseline and recovery. The objective component is
`Σ(s,r) c[s,r] x[s,r]`.

The network model uses integer shipment quantities and integer link capacity
units. A selected shipment consumes its quantity once for every traversal of a
link. Real operational capacity must be converted to an explicitly chosen
integer unit before it enters this model; no implicit rounding is performed.

## Constraints and penalties

Exactly one route per shipment is encoded as:

```text
A * (Σ_r x[s,r] - 1)^2
```

For each binding shared link `l`, let `a[l,s,r]` be the shipment quantity
multiplied by the number of times route `r` traverses `l`. The capacity
inequality is represented exactly as:

```text
Σ(s,r) a[l,s,r] x[s,r] + Σ_b w[l,b] y[l,b] = capacity[l]
A * (left_hand_side - capacity[l])^2
```

The nonnegative binary slack weights cover every integer from zero through
the link capacity and sum exactly to capacity. The final weight may be smaller
than a power of two. For capacity 3, for example, bits of weight 1 and 2
represent slack values 0, 1, 2 and 3. Consequently, over-capacity loads cannot
be hidden by an oversized slack value. Links whose maximum possible selected
load cannot exceed capacity need no slack bits or penalty.

All route scores are nonnegative. The implementation computes
`U = Σ_s max_r c[s,r]` and sets `A = U + 1`. For any valid one-hot assignment,
its objective is at most `U`. Any one-hot or capacity violation has an integer
residual with magnitude at least 1, and therefore receives a penalty of at
least `A`. Thus every infeasible assignment's **full energy**, including the
preserved constant offset, exceeds every feasible objective value. This is a
bound for the current finite candidate model, not a heuristic penalty choice.

The QUBO uses QSupply's ordered-pair convention: each cross term is written
once as `Q[i,j] x[i] x[j]`; no implicit symmetrization is performed. The
expanded squares use `x_i² = x_i`. Their constant terms are returned as
`offset`, separately from `QUBO.energy`. `offset + QUBO.energy(x)` is the full
penalized energy.

## Validation and solver path

`RouteAssignmentQUBO.validate_assignment` validates the complete binary
register and independently checks one-hot selection, shipment/route identity,
route legs against the network and disruption overlay, maximum transit time,
and shared link loads. Its business-metric evaluator re-reads the selected
candidate data. QUBO penalty energy is never treated as proof of operational
feasibility. The evaluation also reports objective contribution, penalty,
offset, QUBO energy and full energy separately, with a reconciliation check.

The exact reference uses `ExactQUBOSolver`; local QAOA uses the existing
`SolverRequest`, QUBO-to-Ising conversion and registered Qiskit/Qulacs adapters.
Each solver's bit assignment is rechecked and rescored by QSupply. The
classical `assign_routes` comparison receives the same finite candidate set,
weights, fixed normalization references, disruption and capacities. Reported
exactness is only over those generated candidates. Candidate-route generation
is bounded and does not guarantee inclusion of every feasible network path.

The API exposes `GET /api/v1/quantum/route-assignment/example` for formulation
metadata and `POST /api/v1/quantum/route-assignment/runs` for exact QUBO,
classical assignment, or an available registered QAOA backend. Unsupported or
unavailable quantum backends are rejected, never silently replaced. Local
Qiskit and Qulacs state-vector runs are classical simulations. No Fujitsu QARP
adapter, quantum hardware execution, general route optimizer or quantum
advantage claim is included.

## Numerical convention and limitations

The route generator and `ObjectiveReferences` currently expose finite Python
floating-point metrics. The formulation converts each finite float using its
exact stored IEEE-754 value (`Fraction.from_float`) and performs subsequent
score and QUBO arithmetic with rational values. This avoids additional
rounding during coefficient expansion and exact enumeration, but can produce
large rational numerators/denominators. It does not make the source route data
more precise than the original float calculations. QAOA adapters ultimately
execute with finite-precision SDK numerics.

The MVP supports at most 12 total variables. A candidate set that exceeds this
limit raises `UnsupportedRouteQUBOError`; options are not silently removed.
The demo is synchronous and uses synthetic data only. It does not model
real-world schedules, customs, multi-commodity shared capacities, time-window
interactions across shipments, or solver performance guarantees.
