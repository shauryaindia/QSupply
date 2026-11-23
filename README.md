 <img width="501" height="501" alt="QSupply Logo" src="https://github.com/user-attachments/assets/9b2c32df-9456-4ea1-b8ae-f8d3fde0ea1c" />

# QSupply

**Enterprise Optimization Platform | Classical, Heuristic & Hybrid Quantum-Classical Optimization**

🌐 **Live Application:** [https://qsupply.macrovisionai.com/](https://qsupply.macrovisionai.com/)

QSupply is an enterprise optimization platform developed by MacroVision AI Pvt. Ltd. It is designed to model, solve, evaluate and benchmark complex optimization problems using mathematical optimization, classical algorithms, heuristics, metaheuristics and emerging hybrid quantum-classical approaches.

With an initial focus on supply chains, logistics and manufacturing, QSupply aims to help enterprises make better operational decisions through solver-agnostic optimization and benchmark-driven evaluation.

> **A product developed and maintained by MacroVision AI Pvt. Ltd.**

---

## Vision

Build a modern optimization platform that enables enterprises and researchers to model, benchmark and solve complex optimization problems using the most appropriate computational approach—whether classical, heuristic, metaheuristic, hybrid or quantum.

## Why QSupply?

Modern enterprises face increasingly complex optimization challenges across supply chains, logistics, manufacturing, scheduling and resource planning. Selecting the right optimization approach is often as important as solving the problem itself.

QSupply brings together Operations Research, Artificial Intelligence and Quantum Computing through a unified, solver-agnostic architecture.

Rather than assuming any single optimization paradigm is universally superior, QSupply aims to benchmark multiple approaches and apply the most appropriate computational method for each problem.

---

## Platform Capabilities

### Optimization Framework
- Mathematical Optimization
- Constraint Optimization
- Multi-objective Optimization
- Optimization Modelling

### Optimization Engines
- Classical Optimization
- Heuristic Optimization
- Metaheuristic Optimization
- Hybrid Quantum-Classical Optimization

### Benchmarking & Evaluation
- Solver Benchmarking
- Performance Analysis
- Optimization Reference Solvers
- Classical vs Hybrid Benchmarking

### Enterprise Optimization
- Supply Chain Optimization
- Logistics & Vehicle Routing
- Production Scheduling
- Inventory Optimization
- Network Design
- Resource Allocation

### Quantum Optimization
- QUBO Modelling and Energy Evaluation
- QUBO-to-Ising Conversion
- QAOA Workflows
- Backend-Neutral Quantum Solver Architecture
- Optional Qiskit and Qulacs Integrations

---

## Framework Integrations

### Implemented Integrations

| Framework / Component | Status | Description |
|---|---|---|
| Qiskit | Implemented | Optional local StatevectorSampler backend |
| Qulacs | Implemented | Optional local CPU statevector simulator |
| FastAPI | Implemented | Backend API |
| React + TypeScript | Implemented | Web application interface |

Qiskit and Qulacs currently provide local classical statevector simulation. These integrations do not represent execution on quantum hardware.

### Planned Integrations

- OR-Tools
- Pyomo
- PuLP
- PennyLane
- Additional optimization and scientific computing frameworks

The presence of a framework in this section does not indicate an existing integration.

---

## Architecture & Design Principles

- Solver-agnostic architecture
- Backend-neutral solver interfaces
- Benchmark-driven optimization
- Modular and extensible design
- Enterprise-first engineering
- Classical and quantum-classical interoperability
- Independent feasibility validation
- Reproducible optimization experiments

---

## Current Development Status

**QSupply is available as a live web application and remains under active development.**

The current platform includes:

- Enterprise optimization dashboard and Control Tower.
- Classical optimization models and solver interfaces.
- CVRP heuristic and exact reference solvers.
- Optimization benchmarking and evaluation.
- Global multimodal network and disruption-recovery demonstrations using synthetic data.
- QUBO modelling and energy evaluation.
- Canonical QUBO-to-Ising conversion.
- Backend-neutral QAOA architecture.
- Optional Qiskit StatevectorSampler and Qulacs CPU statevector integrations.
- Quantum experiment configuration and backend capability discovery.
- Quantum execution metadata, sample evaluation and feasibility validation.
- CSV and PDF reporting for supported dashboard workflows.

**Live Application:** [https://qsupply.macrovisionai.com/](https://qsupply.macrovisionai.com/)

Production data integrations, Fujitsu QARP execution and demonstrated quantum advantage have not yet been established.

---

## Implemented Functionality

### 1. QUBO Energy Evaluation

The repository includes a Python `QUBO` model for named binary variables. It evaluates:

`E(x) = Σ Q[i,j] × x[i] × x[j]`

The implementation validates complete assignments and reports errors for missing, unknown or non-binary values. Boolean assignments (`False`/`True`) are also accepted as 0/1.

See [`src/README.md`](src/README.md) for usage examples and tests.

### 2. Import-Export QUBO Formulation

The dependency-free import-export module formulates shipment-option choices, delay/time/carbon costs, exactly-one selection penalties and shared integer lane capacities as a QUBO.

The constant offset is retained separately. Decoding, original-data feasibility checks and business-cost evaluation are provided independently of QUBO penalty energy.

A small synthetic example uses exhaustive enumeration to verify the formulation. This is not a general-purpose solver.

### 3. QUBO-to-Ising Conversion

`qubo_to_ising` converts the named QUBO model into an Ising Hamiltonian:

`E(z) = C + Σ h[i] z[i] + Σ J[i,j] z[i] z[j]`

Using the convention:

`z[i] = 1 - 2*x[i]`

The conversion:
- Preserves declared variable and register order.
- Combines supplied ordered-pair coefficients for each unordered pair.
- Supports a separate constant offset.
- Preserves exact integer and rational arithmetic where supported.

See [`src/README.md`](src/README.md#qubo-to-ising-conversion).

### 4. Backend-Neutral Solver Architecture

QSupply includes a common solver interface and deterministic `ExactQUBOSolver` for small QUBO problems.

The exact solver supports up to 12 variables by default (4,096 assignments). It is intended as a classical reference for small problems, not a scalable optimizer.

Results distinguish QUBO energy, full energy, Ising energy, domain feasibility and optional business objectives.

### 5. Hybrid Quantum-Classical Optimization and QAOA

QSupply includes a backend-neutral QAOA circuit plan and optional Qiskit and Qulacs execution adapters.

The workflow:
- Converts QUBO models into Ising Hamiltonians.
- Constructs parameterized QAOA circuits.
- Prepares an initial equal-superposition state.
- Applies cost and mixer operations.
- Optimizes circuit parameters using supported optimization methods.
- Samples the resulting state.
- Rescores sampled bitstrings against the original QUBO and constant offset.
- Validates domain feasibility independently.

**Supported optional backends:**

- **Qiskit:** Local StatevectorSampler execution.
- **Qulacs:** Local CPU statevector simulation.

Backend-specific configuration capabilities are exposed through the solver architecture and API.

These integrations currently perform classical statevector simulation. They are not quantum hardware execution, do not establish a performance advantage and should not be interpreted as evidence of quantum advantage.

Fujitsu QARP remains unimplemented and unverified.

Install the relevant optional dependencies using `requirements-qiskit.txt` or `requirements-quantum.txt`.

See [`src/README.md`](src/README.md#optional-qaoa-backends).

### 6. CVRP Route Optimization

The `CVRPProblem` model represents:
- A single depot.
- Customer demands.
- Vehicle capacities.
- A complete distance matrix.

The dependency-free `NearestNeighborTwoOptSolver` constructs capacity-feasible routes and applies 2-opt local search.

A synthetic five-customer, two-vehicle example is available in [`examples/cvrp_synthetic.py`](examples/cvrp_synthetic.py).

This is a heuristic and is not guaranteed to find a globally optimal solution.

### 7. CVRP Benchmarking

The benchmarking engine compares:
- Nearest-neighbour seed solutions.
- 2-opt-improved routes.
- Exact reference solutions.

It evaluates seeded synthetic instances with 5, 7 and 9 customers.

The exact subset dynamic-programming solver is capped at 10 customers because of exponential time and memory growth.

Results include routes, distance, feasibility, vehicles used, wall-clock time and heuristic optimality gap.

Benchmark results are based on synthetic instances and should not be interpreted as real-world performance guarantees.

See [`benchmarks/README.md`](benchmarks/README.md).

### 8. Global Multimodal Network & Disruption Recovery

The global optimization workspace uses a deterministic synthetic network and shipment dataset to generate bounded candidate routes.

It supports:
- Multimodal route comparison.
- Baseline assignment evaluation.
- Simulated corridor disruptions.
- Recovery feasibility analysis.
- Configurable route rankings.
- Per-mode carbon breakdowns.
- Custom disruption scenarios.
- Saved optimization runs.
- CSV and PDF reports.

The synthetic data catalog covers 74 locations and 122 directed links across major trade regions, with six runnable international and domestic demonstration scenarios.

Custom scenarios support closures, unavailable locations, capacity reductions, freight/time multipliers and additive transit delays.

The decision-support endpoint does not use an LLM.

**Important:** The network and scenarios use synthetic data. This is not a live logistics feed or a general-purpose global route optimizer.

See [`docs/global-network.md`](docs/global-network.md) and [`docs/web-api.md`](docs/web-api.md).

---

## Roadmap

### Phase 1 — Core Optimization Foundation
- Core optimization architecture.
- Classical optimization modules.
- CVRP models and solvers.
- Initial benchmarking framework.

**Status:** Implemented.

### Phase 2 — Quantum-Classical Optimization
- QUBO modelling and Ising conversion.
- Backend-neutral solver architecture.
- QAOA workflows.
- Qiskit and Qulacs simulator integrations.
- Quantum experiment evaluation and benchmarking foundations.

**Status:** Initial implementation completed; ongoing development.

### Phase 3 — Enterprise Expansion
- Advanced enterprise optimization workflows.
- Additional solver and framework integrations.
- Expanded optimization problem libraries.
- Production data integrations.
- Scalability and performance improvements.
- Further quantum computing integrations.

**Status:** In progress / planned.

---

## Running QSupply Locally

To run the application from the repository root, use two terminals.

**Terminal 1 — Backend API**

```bash
python3 -m pip install -r requirements-web.txt

PYTHONPATH=src python3 -m uvicorn qsupply.api.app:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — Frontend**

```bash
cd frontend

npm install
npm run dev
```

Open the local dashboard:

[http://127.0.0.1:5173](http://127.0.0.1:5173)

Backend API documentation:

[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

For API tests, install `requirements-web-test.txt`. Run `npm test` and `npm run build` from the `frontend` directory for dashboard tests and production compilation.

---

## Product Access

🌐 **Live Application:** [https://qsupply.macrovisionai.com/](https://qsupply.macrovisionai.com/)

**Developed by MacroVision AI Pvt. Ltd.**

---

## Copyright

© 2026 MacroVision AI Pvt. Ltd. All Rights Reserved.

For questions, collaborations or contributions, please contact **[s@macrovisionai.com](mailto:s@macrovisionai.com)**.
