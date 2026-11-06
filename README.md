<img width="501" height="501" alt="QSupply Logo" src="https://github.com/user-attachments/assets/9b2c32df-9456-4ea1-b8ae-f8d3fde0ea1c" />


# QSupply

QSupply is an enterprise optimization platform under active development, designed to model, solve, and benchmark complex optimization problems using mathematical optimization, heuristics, metaheuristics, and emerging hybrid quantum-classical approaches.

The initial focus is supply chain, logistics, manufacturing, and scheduling optimization, with a long-term vision of supporting enterprise decision intelligence across industries.

> **QSupply is product developed and maintained by MacroVision AI Pvt. Ltd.**

## Vision

Build a modern optimization platform that enables enterprises and researchers to model, benchmark, and solve real-world optimization problems using the most appropriate computational approach—whether classical, heuristic, metaheuristic, hybrid, or quantum.

---

## Why QSupply?

Modern enterprises face increasingly complex optimization challenges across supply chains, logistics, manufacturing, scheduling, and resource planning. Selecting the right optimization approach is often as important as solving the problem itself.

QSupply aims to provide a unified platform for modeling, benchmarking, and solving enterprise optimization problems using mathematical optimization, heuristics, metaheuristics, and emerging hybrid quantum-classical techniques.

Rather than assuming any single optimization paradigm is universally superior, QSupply is built on a solver-agnostic philosophy—benchmarking multiple approaches and applying the most appropriate computational method for each problem.

Our vision is to bridge Operations Research, Artificial Intelligence, and Quantum Computing to enable the next generation of enterprise decision intelligence.

---

## Planned Capabilities

### Optimization Framework

- Mathematical Optimization
- Constraint Optimization
- Multi-objective Optimization
- Optimization Modeling

### Optimization Engines

- Classical Optimization
- Heuristic Optimization
- Metaheuristic Optimization
- Hybrid Quantum-Classical Optimization

### Benchmarking & Evaluation

- Solver Benchmarking
- Performance Analysis
- Standard Optimization Datasets
- Classical vs Hybrid Benchmarking

### Enterprise Optimization

- Supply Chain Optimization
- Logistics & Vehicle Routing
- Production Scheduling
- Inventory Optimization
- Network Design
- Resource Allocation

### Quantum Optimization

- General-purpose QUBO Problem Builder
- QAOA Workflows
- Quantum Solver Integrations
---

## Planned Framework Integrations

The following framework integrations remain planned; their presence here does
not indicate current support:

- OR-Tools
- Pyomo
- PuLP
- Qiskit
- PennyLane
- NumPy
- SciPy

Qulacs is implemented as an optional local simulator integration for the bounded
QAOA workflow described below. It is not a hosted quantum service.

---

## Roadmap

### Phase 1

- Core Optimization Architecture
- Classical Optimization Modules
- Benchmark Framework (initial CVRP benchmarking implemented)

### Phase 2

- Hybrid Optimization Engine
- Quantum Integrations
- Enterprise Optimization Workflows

### Phase 3

- Enterprise APIs
- Performance Benchmarking
- Production Deployment

---

## Design Principles

- Solver-agnostic architecture
- Benchmark-driven optimization
- Modular design
- Enterprise-first engineering
- Hybrid computing where appropriate

---

## Philosophy

QSupply is solver-agnostic.

Rather than assuming a particular optimization paradigm is superior, QSupply aims to benchmark and apply the most appropriate computational approach for each problem—whether mathematical optimization, heuristics, metaheuristics, hybrid methods, or quantum computing.

---


## Status

🚧 QSupply is an early local prototype. It includes tested Python optimization
models, CVRP heuristic and exact solvers, benchmarking, an optional API, and a
browser dashboard. A bounded synthetic multimodal route and disruption-recovery
demonstration is implemented; production data integrations and Qiskit or Fujitsu
quantum services are not.

Current focus:
- System architecture and core optimization framework
- Benchmark problem definitions
- Classical optimization baselines
- Hybrid quantum-classical workflows
- Initial enterprise use cases in supply chain and logistics

The first usable local prototype is available below.

### Implemented functionality: QUBO energy evaluation

The repository now includes a minimal Python `QUBO` model for named binary
variables. It evaluates `E(x) = Σ Q[i,j] × x[i] × x[j]` for a complete
assignment and reports clear errors for missing, unknown, or non-binary
assignment values. Boolean assignments (`False`/`True`) are also accepted as
0/1. See [`src/README.md`](src/README.md) for a usage example and test command.

### Implemented functionality: import-export QUBO formulation

The dependency-free import-export module formulates shipment-option choices,
delay/time/carbon costs, exactly-one selection penalties and shared integer
lane capacities as a QUBO. The constant offset is retained separately;
decoding, original-data feasibility checks and business-cost evaluation are
provided independently of the QUBO penalty energy. A small synthetic example
uses exhaustive enumeration only to verify the five-bit formulation. This is
not a general solver. The optional Qulacs QAOA workflow below currently runs a
separate synthetic QUBO example; Qiskit and Fujitsu QARP integrations remain
unimplemented.

### Implemented functionality: QUBO-to-Ising conversion

`qubo_to_ising` converts the named QUBO model to `C + Σ h[i] z[i] + Σ
J[i,j] z[i] z[j]`, using `z[i] = 1 - 2*x[i]` (bit 0 is spin +1; bit 1 is
spin -1). It combines the QUBO's supplied ordered-pair coefficients for each
unordered pair, preserves declared variable/register order, and accepts a
separate constant offset. Integer and rational coefficients are converted
with exact rational factors. See
[`src/README.md`](src/README.md#qubo-to-ising-conversion).

### Implemented functionality: exact QUBO reference execution

The backend-neutral solver contract and deterministic `ExactQUBOSolver` are
available for small QUBOs. The default maximum is 12 variables (4,096
assignments); it enumerates all assignments and is intended as a classical
reference for future adapters, not a scalable optimizer. Results separate
QUBO/full/Ising energy from
optional domain feasibility and business objective. See
[`src/README.md`](src/README.md#common-solver-contract-and-exact-qubo-reference).

### Implemented functionality: bounded QAOA on optional Qulacs simulator

QSupply includes a backend-neutral QAOA circuit plan and a separate optional
Qulacs CPU state-vector adapter. It prepares an all-`|+>` register, applies
cost evolution for the converted Ising Hamiltonian and an `X` mixer at each
layer, then optimizes angles with seeded SPSA or coordinate search and samples
the final circuit. The initial API limits runs to 12 variables, depth 3, 25
optimizer iterations and 2,048 shots per evaluation. The sample dashboard
workflow uses only a labelled five-variable synthetic import-export QUBO.
Every selected bitstring is rescored against the original QUBO and full offset;
domain feasibility is reported only after the independent validator runs.
This is local classical state-vector simulation, not execution on quantum
hardware, a performance claim, or evidence of quantum advantage. Qiskit and
Fujitsu QARP remain unavailable. Install `requirements-quantum.txt` to enable
the optional adapter. See [`src/README.md`](src/README.md#optional-qulacs-qaoa).

### Implemented functionality: CVRP route heuristic

The `CVRPProblem` model represents a single depot, customer demands, vehicle
capacities, and a complete distance matrix. The dependency-free
`NearestNeighborTwoOptSolver` constructs capacity-feasible routes and applies
2-opt local search, with a synthetic five-customer, two-vehicle example in
[`examples/cvrp_synthetic.py`](examples/cvrp_synthetic.py). It is a heuristic
and is not guaranteed to find a globally optimal solution. Quantum hardware
execution, quantum advantage, and real-world map integration are not
implemented.

### Implemented functionality: CVRP benchmarking

The benchmarking engine compares the nearest-neighbour seed, its 2-opt-improved
routes, and an exact reference on seeded synthetic instances with 5, 7, and 9
customers. The exact subset dynamic program is capped at 10 customers and has
exponential time and memory growth; it is intended only as a small-instance
reference. Results include routes, distance, feasibility, vehicles used,
wall-clock time, and heuristic optimality gap. The gap is measured against the
exact result; heuristic results are not globally optimality claims. See
[`benchmarks/README.md`](benchmarks/README.md).

The exact solver preserves integer/rational distance precision. Each input
Python float is treated as its exact stored IEEE-754 binary value and summed
without intermediate rounding; capacity constraints use the same convention.
Benchmark reports include generated seeds and
instance configuration; heuristic construction failures are reported without
aborting exact evaluation. Timings are single-run observations, not statistical
performance claims.

### Local dashboard and API

The optional FastAPI adapter exposes the CVRP engine and a small global
multimodal demonstration. The global workspace uses a deterministic synthetic
network and shipment set to generate bounded candidate routes, compare a
baseline assignment with simulated corridor disruptions, and report recovery
feasibility and business metrics. The global data catalog covers 74 synthetic
locations and 122 directed links across the major trade regions, with six
runnable international and domestic demonstration scenarios. The map supports
regional, country, transport-mode and location-type filters plus corridor
inspection. The service provides configurable normalized route
rankings, deterministic route analysis and decision support, per-mode carbon
breakdowns, saved custom disruption scenarios, and downloadable CSV/PDF reports
for persisted runs. Custom scenarios support closures, unavailable locations,
capacity reductions, freight/time multipliers and additive transit delays. The
decision-support endpoint does not use an LLM. The map and product overview
identify their inputs as synthetic. This is not a live logistics feed or a
general global route optimizer. See
[`docs/global-network.md`](docs/global-network.md) and
[`docs/web-api.md`](docs/web-api.md) for assumptions, APIs and limitations.

To start the application from the repository root, use two terminals:

```sh
# Terminal 1: optional Python API dependencies, then start the API
python3 -m pip install -r requirements-web.txt
PYTHONPATH=src python3 -m uvicorn qsupply.api.app:app --reload --host 127.0.0.1 --port 8000

# Terminal 2: install frontend dependencies, then start Vite
cd frontend
npm install
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). For the backend API docs,
open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs). Install
`requirements-web-test.txt` to run the API tests; run `npm test` and `npm run
build` from `frontend` for dashboard tests and production compilation.

---


## Copyright

© 2026 MacroVision AI Pvt. Ltd. All Rights Reserved.

For questions, collaborations, or contributions, please contact **s@macrovisionai.com**.
