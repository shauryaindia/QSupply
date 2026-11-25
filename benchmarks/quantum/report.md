# Synthetic multimodal route study

Each shipment selects one generated route. The objective is the priority-weighted sum of baseline-normalized freight and delay cost, time, carbon and disruption exposure.

For route bits x, add A(Σx−1)² per shipment and A(load + slack − capacity)² per binding link. A is one plus the sum of maximum per-shipment route scores. Substituting x=(1−z)/2 gives the Ising Hamiltonian. The constant is restored when scoring samples.

Portfolio generation seed 7102. Four preset sizes were selected before sampling. Both local simulators used depth 1, SPSA, two iterations, 64 shots per evaluation and seeds 11, 22, 33, 44, 55. Each method used the same candidates, weights and baseline normalization within its case.

For ordered-pair Q, write aᵢⱼ=Qᵢⱼ+Qⱼᵢ for i<j. In H=C+Σhᵢzᵢ+ΣJᵢⱼzᵢzⱼ, Jᵢⱼ=aᵢⱼ/4, hᵢ=−Qᵢᵢ/2−Σⱼ≠ᵢaᵢⱼ/4 (using symmetric pair totals), and C=offset+ΣQᵢᵢ/2+Σᵢ<ⱼaᵢⱼ/4.

## Instances

| ID | Shipment IDs | Route cap | Candidates | Bits | Overlay | Weight profile |
|---|---|---:|---:|---:|---|---|
| route-qubo-8 | EXP-104, EXP-407 | 3 | 6 | 8 | synthetic-route-qubo-shanghai-access-capacity | balanced |
| route-qubo-10 | EXP-104, EXP-205, EXP-306 | 3 | 8 | 10 | synthetic-route-qubo-shanghai-access-capacity | carbon |
| route-qubo-11 | EXP-104, EXP-407, EXP-508 | 3 | 9 | 11 | synthetic-route-qubo-shanghai-access-capacity | balanced |
| route-qubo-12 | EXP-104, EXP-205, EXP-407, EXP-508 | 3 | 12 | 12 | Baseline | time |
| portfolio-01 | EXP-104, EXP-205 | 2 | 4 | 4 | Baseline | time |
| portfolio-02 | DOM-710, EXP-104, EXP-508 | 3 | 9 | 9 | synthetic-singapore-customs-delay | carbon |
| portfolio-03 | EXP-205, EXP-407, EXP-508 | 2 | 6 | 6 | synthetic-suez-capacity-restriction | time |
| portfolio-04 | EXP-205, EXP-609 | 3 | 5 | 5 | synthetic-china-us-port-closure | time |
| portfolio-05 | DOM-710, EXP-205 | 2 | 4 | 4 | Baseline | balanced |
| portfolio-06 | EXP-306, EXP-609 | 3 | 4 | 4 | synthetic-singapore-customs-delay | carbon |
| portfolio-07 | DOM-710, EXP-609 | 2 | 4 | 4 | synthetic-suez-capacity-restriction | balanced |
| portfolio-08 | EXP-104, EXP-306 | 3 | 5 | 5 | synthetic-china-us-port-closure | balanced |
| portfolio-09 | DOM-710, EXP-306, EXP-609 | 2 | 6 | 6 | Baseline | time |
| portfolio-10 | EXP-205, EXP-508 | 3 | 6 | 6 | synthetic-singapore-customs-delay | carbon |
| portfolio-11 | DOM-710 | 2 | 2 | 2 | synthetic-suez-capacity-restriction | time |
| portfolio-12 | DOM-710, EXP-407 | 3 | 6 | 6 | synthetic-china-us-port-closure | time |
| portfolio-13 | DOM-710, EXP-306 | 2 | 4 | 4 | Baseline | time |
| portfolio-14 | DOM-710, EXP-407, EXP-609 | 3 | 8 | 8 | synthetic-singapore-customs-delay | time |
| portfolio-15 | EXP-104, EXP-205, EXP-508 | 2 | 6 | 8 | synthetic-suez-capacity-restriction | balanced |
| portfolio-16 | EXP-104, EXP-508, EXP-609 | 3 | 8 | 8 | synthetic-china-us-port-closure | time |
| size-control | DOM-710, EXP-104, EXP-205, EXP-306, EXP-407, EXP-508, EXP-609 | 3 | 19 | 19 | Baseline | balanced |

Balanced weights are 40/25/20/15 for cost/time/carbon/exposure. Carbon and time profiles give their named metric 100%.

## Measured results

| Instance | Method | Feasible / trials | Optimal rate | Best objective | Mean feasible gap (%) | Mean solver time (s) |
|---|---|---:|---:|---:|---:|---:|
| route-qubo-8 | exact-qubo | 1/1 | — | 0.9178 | 0 | 0.01978 |
| route-qubo-8 | classical-assignment | 1/1 | — | 0.9178 | 0 | 0.001715 |
| route-qubo-8 | qiskit | 3/5 | 0.2 | 0.9178 | 1.62 | 0.08546 |
| route-qubo-8 | qulacs | 4/5 | 0.6 | 0.9178 | 0.2805 | 0.06622 |
| route-qubo-10 | exact-qubo | 1/1 | — | 0.5787 | 0 | 0.07057 |
| route-qubo-10 | classical-assignment | 1/1 | — | 0.5787 | 0 | 0.002213 |
| route-qubo-10 | qiskit | 2/5 | 0 | 0.636 | 38.29 | 0.1042 |
| route-qubo-10 | qulacs | 3/5 | 0 | 0.6005 | 43.19 | 0.07364 |
| route-qubo-11 | exact-qubo | 1/1 | — | 0.8007 | 0 | 0.1684 |
| route-qubo-11 | classical-assignment | 1/1 | — | 0.8007 | 0 | 0.002503 |
| route-qubo-11 | qiskit | 4/5 | 0.2 | 0.8007 | 6.707 | 0.1373 |
| route-qubo-11 | qulacs | 4/5 | 0 | 0.8095 | 7.426 | 0.08887 |
| route-qubo-12 | exact-qubo | 1/1 | — | 0.7333 | 0 | 0.2535 |
| route-qubo-12 | classical-assignment | 1/1 | — | 0.7333 | 0 | 0.002828 |
| route-qubo-12 | qiskit | 3/5 | 0 | 0.7369 | 7.912 | 0.1398 |
| route-qubo-12 | qulacs | 3/5 | 0 | 0.7369 | 3.655 | 0.06258 |
| portfolio-01 | exact-qubo | 1/1 | — | 0.9707 | 0 | 0.001433 |
| portfolio-01 | classical-assignment | 1/1 | — | 0.9707 | 0 | 0.001065 |
| portfolio-02 | exact-qubo | 1/1 | — | 0.3965 | 0 | 0.02059 |
| portfolio-02 | classical-assignment | 1/1 | — | 0.3965 | 0 | 0.002385 |
| portfolio-03 | exact-qubo | 1/1 | — | 0.8195 | 0 | 0.00347 |
| portfolio-03 | classical-assignment | 1/1 | — | 0.8195 | 0 | 0.001968 |
| portfolio-04 | exact-qubo | 1/1 | — | 0.8195 | 0 | 0.002166 |
| portfolio-04 | classical-assignment | 1/1 | — | 0.8195 | 0 | 0.002004 |
| portfolio-05 | exact-qubo | 1/1 | — | 0.8748 | 0 | 0.001473 |
| portfolio-05 | classical-assignment | 1/1 | — | 0.8748 | 0 | 0.001087 |
| portfolio-06 | exact-qubo | 1/1 | — | 0.09756 | 0 | 0.001503 |
| portfolio-06 | classical-assignment | 1/1 | — | 0.09756 | 0 | 0.001163 |
| portfolio-07 | exact-qubo | 1/1 | — | 0.3469 | 0 | 0.001562 |
| portfolio-07 | classical-assignment | 1/1 | — | 0.3469 | 0 | 0.001166 |
| portfolio-08 | exact-qubo | 1/1 | — | 0.5245 | 0 | 0.002152 |
| portfolio-08 | classical-assignment | 1/1 | — | 0.5245 | 0 | 0.001432 |
| portfolio-09 | exact-qubo | 1/1 | — | 0.5481 | 0 | 0.002853 |
| portfolio-09 | classical-assignment | 1/1 | — | 0.5481 | 0 | 0.001475 |
| portfolio-10 | exact-qubo | 1/1 | — | 0.4354 | 0 | 0.003236 |
| portfolio-10 | classical-assignment | 1/1 | — | 0.4354 | 0 | 0.001595 |
| portfolio-11 | exact-qubo | 1/1 | — | 0.5149 | 0 | 0.000724 |
| portfolio-11 | classical-assignment | 1/1 | — | 0.5149 | 0 | 0.0005885 |
| portfolio-12 | exact-qubo | 1/1 | — | 0.785 | 0 | 0.003005 |
| portfolio-12 | classical-assignment | 1/1 | — | 0.785 | 0 | 0.001541 |
| portfolio-13 | exact-qubo | 1/1 | — | 0.5387 | 0 | 0.001427 |
| portfolio-13 | classical-assignment | 1/1 | — | 0.5387 | 0 | 0.001006 |
| portfolio-14 | exact-qubo | 1/1 | — | 0.6359 | 0 | 0.009709 |
| portfolio-14 | classical-assignment | 1/1 | — | 0.6359 | 0 | 0.002142 |
| portfolio-15 | exact-qubo | 0/1 | — | — | — | 0.01424 |
| portfolio-15 | classical-assignment | infeasible | — | — | — | 0.001201 |
| portfolio-16 | exact-qubo | 1/1 | — | 0.593 | 0 | 0.009432 |
| portfolio-16 | classical-assignment | 1/1 | — | 0.593 | 0 | 0.002111 |
| size-control | classical-assignment | 1/1 | — | 0.5508 | — | 0.005677 |
| size-control | exact-qubo | unavailable | — | — | — | — |

## Observations

- Qiskit returned 12 feasible plans across 20 requested trials. 2 matched the exact candidate-set objective.
- Qulacs returned 14 feasible plans across 20 requested trials. 3 matched the exact candidate-set objective.
- portfolio-15: No feasible plan over these candidates.
- size-control: route assignment requires 19 binary variables (19 route choices, 0 capacity slack); the current exact/QAOA limit is 12. Reduce the explicitly selected candidate set or shipment scope and formulate again.

## Simulator execution

Local Python 3.13.3, Qiskit 2.6.2 and Qulacs 0.6.14. Depth below is the native circuit depth before measurement. Evaluations count optimizer sampling calls, excluding the final measurement.

| Case | Simulator | Circuit depth | Optimizer evaluations across trials |
|---|---|---:|---:|
| route-qubo-8 | qiskit | 15 | 35 |
| route-qubo-8 | qulacs | 39 | 35 |
| route-qubo-10 | qiskit | 15 | 35 |
| route-qubo-10 | qulacs | 39 | 35 |
| route-qubo-11 | qiskit | 15 | 35 |
| route-qubo-11 | qulacs | 39 | 35 |
| route-qubo-12 | qiskit | 6 | 35 |
| route-qubo-12 | qulacs | 12 | 35 |

Feasibility counts evaluate the returned minimum-energy sample of each completed trial. Success is the fraction of requested seeded trials with an independently feasible assignment matching the exact business objective. Missing seed confirmation gives an unavailable rate. Objective gaps average only validated feasible outcomes with a nonzero reference. Exact fractions and individual violations are in runs.json.

## Scaling and limitations

Exact enumeration doubles its search space with each additional bit. The size-control case exceeds the 12-bit guard. Its exact reference and gap are unavailable, and its classical objective uses the route planner’s native floating-point score. All other references apply only to generated candidates. Three different objective profiles and different networks of candidates prevent attributing observed changes solely to size.

Solver timings are local observations and exclude candidate generation. Optimizer and sampling times overlap. Native SDK gate depths depend on gate decomposition. Five seeds give success rates in increments of 20 percentage points. A larger paired seed study across matched capacities and objective profiles would improve uncertainty estimates.

Reproduce from the repository root with the supported SDKs installed in an isolated environment: `PYTHONPATH=src python examples/quantum_research.py OUTPUT_DIRECTORY`. The directory receives this report, study.json, runs.json and summary.csv. Machine timings vary.
