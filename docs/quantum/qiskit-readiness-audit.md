# QSupply Qiskit Architecture and Readiness Audit

**Audit date:** 2026-11-06
**Scope:** Read-only inspection and integration planning. No application code,
frontend, dependencies, deployment configuration, or Git history was changed.

## 1. Executive summary

QSupply has a solid first layer for adding another QAOA execution adapter:
named QUBO and Ising models, an exact QUBO reference solver, a common
`SolverRequest`/`SolverResult` contract, and a backend-neutral parameter
optimizer that delegates sampling through a callback. Qulacs is currently an
optional, lazily imported CPU state-vector simulator.

The architecture is **partly solver-agnostic, but not yet safely interchangeable
at the circuit layer**. In particular, `build_qaoa_circuit_plan` emits rotation
angles in the Qulacs gate-sign convention. A Qiskit adapter that maps those
instructions directly to Qiskit `rz`/`rx` gates would implement the opposite
unitary for those rotations. Before adding Qiskit, move sign and circuit
translation details behind backend-specific compilers and add cross-backend
unitary/energy tests.

Other important gaps are that the current benchmark helper cannot pass one
request to both exact QUBO and QAOA Ising solvers because their declared
representations differ, quantum runs are not persisted, and the API/dashboard
only expose the fixed Qulacs synthetic example. Qiskit should be added as an
optional local simulator adapter, reusing QSupply's `run_qaoa` optimizer and
independent validation rather than adding a second QAOA algorithm package.

**Recommendation:** use current Qiskit SDK circuits and primitives for the
adapter, initially with `qiskit.primitives.StatevectorSampler`. Keep
`qiskit-aer` optional for alternate high-performance/noisy local simulation.
Do not base this milestone on `qiskit-optimization`: the project is archived,
and the current release's documented SDK compatibility tops out below the
current Qiskit SDK version. No Qiskit-related package is installed in the active
Python environment.

## 2. Repository and Git inspection

- Branch: `main`.
- HEAD: `acb0ba0 Add Qulacs QAOA execution milestone`.
- Working tree: clean at inspection time.
- Local branch: three commits ahead of `origin/main`; no local/remote
  reconciliation or Git mutation was performed.
- Relevant history is intact:
  - `19ee356 Add canonical QUBO-to-Ising conversion`
  - `891efec Add common solver interface and exact QUBO reference solver`
  - `acb0ba0 Add Qulacs QAOA execution milestone`
- Python: CPython 3.13.3.
- Dependency management: flat optional `requirements-*.txt` files; no
  `pyproject.toml`, `setup.py`, or `setup.cfg` was found. Core modules are
  designed to import without web or quantum SDKs.
- In the active Python environment, Qiskit, Aer, Qiskit Optimization,
  Qiskit Algorithms, Qulacs and SciPy are absent; NumPy is present. Qulacs is
  declared only in `requirements-quantum.txt` and was previously tested in a
  separate temporary environment.
- Test conventions: Python `unittest` under `tests/`, with optional-dependency
  integration tests skipped when the package is missing; frontend uses Vitest.

## 3. Current architecture assessment

### QUBO and Ising mathematics

[`src/qsupply/qubo.py`](../../src/qsupply/qubo.py) evaluates the documented
ordered-pair objective exactly as supplied:

`E(x) = Σ Q[i,j] x[i] x[j]`.

It preserves declared variable order, validates complete assignments and
coefficient keys, and does not silently symmetrize the matrix.

[`src/qsupply/ising.py`](../../src/qsupply/ising.py) uses
`z_i = 1 - 2x_i` (binary zero maps to spin `+1`; one maps to `-1`). For each
unordered pair, it first combines `a_ij = Q[i,j] + Q[j,i]`. With a separate
constant offset `o`, its conversion is:

- `C = o + Σ_i Q[i,i]/2 + Σ_{i<j} a_ij/4`
- `h_i = -Q[i,i]/2 - Σ_{j != i} a_ij/4`
- `J_ij = a_ij/4`

The Ising model preserves QUBO order through `variable_indices`, and evaluates
`C + Σ h_i z_i + Σ J_ij z_i z_j`. Integer and rational coefficients retain
exact arithmetic where supported. This is an appropriate canonical input for
both Qulacs and Qiskit; the backend adapters must not independently redo this
conversion or drop `C` from reported energy.

### Solver contracts and exact reference

[`src/qsupply/solver.py`](../../src/qsupply/solver.py) defines:

- `SolverMetadata` with backend category and supported representations.
- `SolverRequest`, containing the source QUBO, offset, selected
  representation, a canonically checked Ising model, and optional independent
  validator/decoder/business-objective callbacks.
- `SolverResult`, which records binary/spin assignments, QUBO/full/Ising
  energies, feasibility, measurements and backend metadata.
- A runtime-checkable `Solver` protocol.
- `ExactQUBOSolver`, which enumerates all assignments up to its default
  12-variable limit.

The exact solver declares QUBO support only. Qulacs QAOA declares Ising
support only. The current `benchmark_solvers(request, solvers)` requires one
representation and rejects a solver that does not support it. It therefore
cannot directly benchmark ExactQUBO and QAOA together using one request. This
needs a benchmark-case layer that builds equivalent per-solver requests from
the same canonical QUBO, offset, callbacks, seed and objective definition.

### QAOA and Qulacs

[`src/qsupply/qaoa.py`](../../src/qsupply/qaoa.py) contains `QAOAConfig`,
`run_qaoa`, an SDK-neutral sampling callback shape, sample/result structures,
and a gate-plan builder. It implements bounded seeded SPSA and coordinate
search. Its current limits are 12 variables, depth 1–3, 16–2,048 shots, and
1–25 optimizer iterations. Cost coefficients are divided by the maximum
absolute nonconstant Ising coefficient for angle optimization; discrete
samples are rescored using the original model.

[`src/qsupply/backends/qulacs.py`](../../src/qsupply/backends/qulacs.py)
keeps Qulacs imports lazy, creates and evolves a circuit per parameter
evaluation, seeds Qulacs sampling, decodes Qulacs integer samples as bit `i` of
qubit `i`, recalculates QUBO/full/Ising energy, and invokes the independent
validator before reporting a plan as feasible. If the optional dependency is
absent, capability reporting says so and the endpoint returns an unavailable
response instead of substituting another simulator.

### API, dashboard, examples and tests

- `src/qsupply/api/app.py` exposes `GET /api/v1/capabilities` and
  `POST /api/v1/quantum/qubo-runs`. The latter is a bounded, synchronous run on
  one fixed synthetic five-variable import-export formulation. It compares
  against exact enumeration when requested. It has no backend selector or
  persisted quantum run history.
- `src/qsupply/api/schemas.py` defines constrained request fields and a
  normalized response containing backend identity, energies, final counts,
  sample count, timing, feasibility and decoded synthetic business metrics.
- `frontend/src/App.tsx` displays dynamic Qulacs availability and a real Qulacs
  request workflow. Qiskit is accurately shown as not implemented; the page
  does not yet select between solvers. A lower “Quantum adapters” card still
  says “Planned” despite Qulacs being implemented and should be updated during
  a later dashboard change.
- `examples/qulacs_qaoa.py`, `tests/test_qaoa.py` and
  `tests/test_quantum_api.py` cover the current single backend and synthetic
  case. The tests cover the cost unitary, bit ordering, reproducibility, exact
  comparison, feasibility and missing optional Qulacs.

## 4. Strengths and architectural gaps

### Strengths to preserve

1. QUBO and Ising are named-variable, dependency-free core models.
2. The offset is preserved separately and checked through energy equivalence.
3. A domain feasibility callback is independent of penalized QUBO energy;
   decoded business output is produced only for feasible best samples.
4. QAOA's parameter search is already separated from the SDK sampling
   callback, so two adapters can share its optimizer and result calculation.
5. Optional imports are isolated and capabilities report actual backend
   availability.
6. The existing exact QUBO solver is a useful reference for small instances.

### Gaps and risks before Qiskit work

1. **Gate-sign convention leaks from Qulacs.** The QAOA plan currently stores
   negative RZ/RX angles because Qulacs rotation gates use the opposite
   exponential sign from Qiskit's standard `RZ`/`RX` convention. This is
   documented in `build_qaoa_circuit_plan`. A direct translation would invert
   cost and mixer evolution. Make the shared plan describe mathematical
   rotations (`exp(-i θP/2)`) or Hamiltonian terms; translate signs in each
   backend compiler. Add independent unitary tests for cost and mixer in both
   backends.
2. **No common backend protocol.** `Solver` is a common algorithm/result
   contract; `SampleFunction` is a callable shape, but backend availability,
   version, compilation, timing scope and error contracts are specific to
   Qulacs today. Add a small `QAOASamplingBackend` protocol or equivalent
   adapter metadata while preserving `Solver`.
3. **Representation mismatch blocks generic benchmarking.** Exact advertises
   QUBO; QAOA advertises Ising. A benchmark-case must derive their requests
   from one canonical case and assert the same objective/offset. The current
   `benchmark_solvers` cannot do that itself.
4. **Measurement counts have different meanings.** `SolverResult.sample_count`
   includes optimizer and final-batch shots, while `sample_frequencies`
   contains final-batch frequencies only. Also, QAOA currently places total
   measurements in `candidate_assignments_evaluated`, although shots can
   repeat assignments. Benchmark reporting must distinguish unique candidates,
   total measured shots and final-batch shots.
5. **Time scopes must be normalized.** Qulacs `circuit_execution_time_seconds`
   sums circuit construction, state evolution and sampling across every
   optimizer evaluation plus final sampling; its `optimization_time_seconds`
   includes callback sampling while the API `elapsed_seconds` includes the
   whole adapter call. Future Qiskit records must define the same scopes and
   separately identify transpilation, queue/wall time and backend execution
   where applicable.
6. **QAOA result is not an experiment record.** Runs have an in-memory UUID and
   no persistent history. This can remain out of an initial backend adapter,
   but should be an explicit product/API decision rather than implied by the
   current CVRP run store.
7. **Circuit reuse and compilation.** Qulacs rebuilds the numeric circuit for
   every objective evaluation. Qiskit can construct a parameterized circuit
   once and bind parameters, but adding this optimization should not alter the
   shared QAOA objective/sample semantics.
8. **API execution is synchronous.** Current limits and fixed five-variable
   example keep the route small, but future larger cases or remote hardware
   require bounded request time, cancellation and truthful queued/running/job
   states rather than blocking a web worker.

## 5. Qiskit packages and APIs

Official documentation and package metadata were checked on 2026-11-06.

### Recommended initial package set

| Package | Recommendation | Reason |
| --- | --- | --- |
| `qiskit` | Required for Qiskit adapter | Core `QuantumCircuit`, `SparsePauliOp`, `QAOAAnsatz`, transpiler and `StatevectorSampler` APIs. Current PyPI release is 2.6.1 and requires Python 3.10+, compatible with repository Python 3.13.3. |
| `qiskit-aer` | Optional extra, not required for first adapter | Alternative local simulator with V2 sampler, additional simulation methods and noise models. Current 0.18.2 release has CPython 3.13 macOS ARM64 wheels. The project page currently reports reduced-maintenance mode; pin/test it separately and do not make core Qiskit depend on it. |
| `qiskit-optimization` | Do not add | It is archived and no longer supported by IBM; the ecosystem compatibility table lists Qiskit support only through 2.4.1 while the SDK is now 2.6.1. Its algorithms and converters are unnecessary because QSupply already owns the model, conversion, QAOA loop and validator. |
| `qiskit-ibm-runtime` | Out of scope for local adapter | Needed only for a later IBM Runtime/hardware connection. It introduces account credentials, service/backend selection, hardware transpilation, queue and job lifecycle concerns. Do not install or configure it for local simulation. |
| `qiskit-algorithms` | Avoid for this milestone | QSupply already has a QAOA optimizer loop. Older Qiskit algorithm APIs are version-sensitive; avoid duplicating algorithm state/optimizer behavior with an additional package. |
| SciPy | Not needed for initial QSupply QAOA | Current `run_qaoa` uses its own bounded SPSA/coordinate optimizers. Add only if a deliberate optimizer extension needs SciPy. |

The current official Qiskit docs show `QAOAAnsatz(cost_operator, reps, ...)`
for parameterized cost/mixer circuit construction and `StatevectorSampler`
as the core SDK reference sampler. The sampler accepts shots and a seed.
For the initial implementation, QSupply should continue to own the QAOA
optimization loop and consume a small Qiskit adapter that implements the
existing sampling callback. This avoids binding solver behavior to an archived
optimization package or to one sampler implementation.

For local simulator use, Qiskit 2.x `QuantumCircuit` plus
`qiskit.primitives.StatevectorSampler` is the smallest dependency set. Aer may
be added as a separately installable optional performance/noise extra after
testing on supported deployment platforms. Hardware execution is a distinct
backend class and must not be labeled available merely because `qiskit` is
installed.

## 6. Qulacs and Qiskit comparison

| Concern | Current Qulacs | Qiskit recommendation |
| --- | --- | --- |
| Circuit construction | QSupply converts its gate plan to Qulacs gates. | Qiskit `QuantumCircuit`; optionally build a parameterized circuit once and bind values per evaluation. Move rotation sign translation behind backend adapter. |
| Simulator | `QuantumCircuit` + `QuantumState`, CPU state vector. | Core `StatevectorSampler` for minimum dependencies; optional Aer V2 sampler for another local simulator/methods. |
| State preparation | H on every qubit. | Same H initial state via QAOA ansatz/default or explicit gates. |
| Cost/mixer | Explicit RZ, CX-RZ-CX, RX gates. | `SparsePauliOp`/`QAOAAnsatz` or explicit parameterized circuit. Verify identical exponent signs and the `z=1-2x` mapping. |
| Sampling | Seed passed to `QuantumState.sampling`; raw integer bit `i` maps to qubit `i`. | V2 sampler result is organized by classical-register data; Qiskit count strings display register bits in printed order. Use one explicit register and a tested parser that maps displayed bit strings back to QSupply's variable order. |
| Optimizer | Shared QSupply seeded SPSA or coordinate loop. | Reuse `run_qaoa`; do not add a second QAOA optimizer unless adding a separately named, documented option. |
| Timing | Counts construction/evolution/sampling around each Qulacs callback. | Measure circuit build/transpile separately from sampler job execution and orchestration. Do not equate simulator time with remote QPU time. |
| Optional dependency | Lazy `importlib` import; capability probe and explicit unavailable result. | Same lazy adapter pattern; capability probe should import/inspect the Qiskit package without loading it during core QSupply import. Aer availability is separate from Qiskit availability. |

The Qiskit adapter can share `run_qaoa`, Ising energy/scaling, exact sample
rescoring, feasibility and result normalization. It should own SDK-specific
operator/circuit construction, transpilation, sampler creation, measurement
register layout, count parsing, simulator metadata and SDK exceptions. Preserve
one source of truth for variable ordering and binary/spin conversion.

## 7. Proposed backend-neutral architecture

Keep the existing pipeline and refine its circuit boundary:

```text
Domain problem -> QUBO + offset -> IsingModel -> QAOAConfig/run_qaoa
                                      |                  |
                     exact QUBO solver            SampleBackend
                                                   /           \
                                      Qulacs adapter       Qiskit adapter
                                                   \           /
                            SampleBatch -> QUBO/Ising rescoring -> domain validator
                                      -> normalized SolverResult / BenchmarkRecord
```

Recommended interfaces:

- `Solver.solve(SolverRequest) -> SolverResult` stays the public solver
  contract.
- A narrow `QAOASamplingBackend.sample(ising, gammas, betas, shots, seed)`
  returns `SampleBatch`; backend metadata/capability are exposed separately.
- `run_qaoa` stays the single owner of angle initialization, updates,
  optimizer budgets, best parameters, final samples and QAOA-level stats.
- Backend circuit compilation uses mathematical rotation semantics, with
  Qulacs/Qiskit angle conversion localized in each adapter.
- Backend adapters return sampled bits in `IsingModel.variables` order. They
  do not return SDK-specific bitstrings beyond optional diagnostic metadata.
- The solver adapter recalculates original QUBO energy, offset-inclusive
  energy, Ising energy, feasibility and business objective for the best sample.
- Exact solver remains a separate classical `Solver`; do not present it as a
  QAOA backend or simulator.

## 8. Benchmark design

Introduce a `QUBOBenchmarkCase` (name can change) with a single immutable source
QUBO, constant offset, optional independent validator/decoder/business metric,
stable case ID, and dataset metadata/seed. For each solver, construct the
native `SolverRequest` from that same case: QUBO representation for exact
enumeration and Ising representation for QAOA. Before recording results,
assert identical variable order, objective, offset and validation callback.

Each record should report:

- Exact full energy and exact assignment (only for supported small instances).
- QAOA best sampled full energy, absolute energy gap, and relative gap
  `100 * (best - exact) / abs(exact)` only when the exact reference is
  nonzero; otherwise relative gap is unavailable.
- Final-batch and total optimizer measurement counts separately, best sample
  frequency, mean sampled full energy, feasible final-shot fraction and
  whether the best sample independently validates.
- Business objective only for a feasible decoded solution.
- Variable count, depth, seed, optimizer and iteration/evaluation count,
  backend/version and normalized timing scopes.
- Multiple seed/repetition summaries (median, spread and individual runs),
  not one timing presented as a stable performance claim.

For fair comparisons, keep the source problem and objective fixed. Compare
Qulacs and Qiskit under the same depth, angle optimizer, initialization,
objective-evaluation shot budget and final shots. Also report total shots and
number of objective evaluations because a nominal optimizer iteration can
contain different numbers of sampling calls. Exact enumeration uses candidate
evaluations, not quantum shots, so it is an objective-quality reference rather
than a like-for-like throughput comparison. Report local Qulacs, Qiskit
state-vector and Aer simulator timings as different simulator categories.
Any future QPU numbers must separately show submission/queue, QPU execution,
classical orchestration and wall-clock duration.

## 9. API and dashboard integration plan

Minimum follow-on changes:

1. Add `qiskit-qaoa` to `/api/v1/capabilities`, with states such as
   `available`, `optional_dependency_missing` and `execution_error` kept
   distinct. Report backend type (`simulator`) and package/simulator version.
2. Extend the quantum request with an explicit backend ID (`qulacs` or
   `qiskit-statevector` initially), preserving existing defaults/API
   compatibility where possible. Reject unknown or unavailable backend IDs
   clearly; never substitute Qulacs when Qiskit was selected.
3. Reuse the existing fixed synthetic import-export example, exact reference,
   validators, objective and response fields. Add per-backend runtime
   configuration metadata and separate measurement totals from final counts.
4. In the dashboard, add an explicit backend selector populated from
   capabilities. Disable unavailable choices, display “local state-vector
   simulator” for both local options, and keep the existing p/optimizer/
   iteration/shots/seed controls. Show exact comparison, feasibility and
   timings with the simulator/backend name.
5. Do not add real hardware/account credentials, persisted quantum run history,
   global multimodal QAOA, or a dashboard redesign in the Qiskit adapter
   milestone unless separately approved.

## 10. Dependency, compatibility and resource limits

The active environment is Python 3.13.3 and has no Qiskit packages. PyPI
currently lists Qiskit 2.6.1 with Python `>=3.10`; Aer 0.18.2 publishes a
CPython 3.13 macOS ARM64 wheel, so the observed local platform has package
artifacts available. Do not install during this audit. Validate the exact
locked pair in an isolated environment before changing any dependency file.

Recommended optional files for implementation:

- `requirements-qiskit.txt`: bounded `qiskit` 2.x dependency.
- Optional separate `requirements-qiskit-aer.txt` including the Qiskit set
  plus a tested `qiskit-aer` version. Keep Aer out of the minimum local SDK
  route.

Initial conservative service limits should match existing boundaries until
benchmarks establish otherwise:

| Resource | Initial recommendation | Rationale |
| --- | --- | --- |
| Variables | 12 maximum for local state-vector Qiskit/Qulacs | `2^n` state vector grows exponentially; retain the existing core cap. |
| Depth | 1–3 | Keeps circuit depth and current test scope modest. |
| Shots per evaluation | 16–2,048 | Existing cap; enforce a total shot/evaluation budget as well. |
| Optimizer iterations | 1–25 | Existing cap; define `max_iterations` as updates and report actual evaluations. |
| Timeout | 30 seconds initial API wall-clock ceiling, configurable server-side | Protect synchronous API worker; combine with a maximum total circuit-evaluation/shot budget. Validate in deployment-like conditions. |
| Memory | Treat dense state-vector estimate as at least `16 * 2^n` bytes per complex128 vector, plus simulator/circuit/transpiler overhead | Use a conservative safety factor (e.g. 4x) in admission checks; a process-level memory limit is stronger than an estimate. |

Qiskit and Qulacs should return the common failed result with explicit backend
identity and sanitized error text for optional-package, compilation,
simulation, sampling, timeout or result-decoding errors. Do not log credentials
or raw environment values. A timeout must not leave the run mislabeled as
completed; if in-process native calls cannot be safely interrupted, isolate
work in a cancellable worker/process before exposing larger limits.

## 11. Testing strategy

- Keep core test runs working with no Qiskit/Aer installed; import core QSupply
  and `qsupply.backends` without SDK imports.
- Unit-test Qiskit operator coefficients and QUBO/Ising energy equivalence on
  every assignment for small models containing diagonal, one-sided and
  two-orientation coefficients, constants, negative and rational values.
- Test the mathematical circuit unitary (including rotation sign) on all
  basis states for a small Ising model; compare Qiskit and Qulacs plans under
  one canonical convention.
- Test variable-to-qubit mapping and a deterministic basis-state measurement
  to prove Qiskit's printed classical bitstring is decoded in QUBO order.
- Test sampler shot count, seed-repeatability, configured seed propagation,
  zero/negative invalid settings, unsupported size/depth and malformed
  sampler output.
- Test missing SDK, Aer missing while Qiskit is present, Qiskit errors, and
  non-fallback behavior.
- Run ExactQUBO, Qulacs QAOA and Qiskit QAOA on the exact same 5-bit synthetic
  QUBO; compare energies, feasible rate, decoded plan and objectives. Do not
  assert that stochastic QAOA always finds the optimum unless a fixed small
  seed/test instance intentionally makes that test deterministic.
- API integration tests should cover capability state, explicit backend
  selection, unavailable backend, invalid request and exact comparison.
- Frontend tests should cover selector options, disabled unavailable backend,
  request payload, loading/error/result states and backend-specific result
  identity. Regenerate OpenAPI types from the API schema.
- Run the full Python suite without optional quantum packages, then optional
  Qulacs and Qiskit suites in isolated environments; run frontend tests,
  TypeScript typecheck, production build and `git diff --check`.

## 12. Estimated effort

Assuming one engineer familiar with the current repository, the Qiskit
state-vector adapter milestone is approximately **4–6 engineering days**:

- 0.5–1 day: abstract rotation semantics and backend interface, strengthen
  circuit equivalence tests.
- 1–1.5 days: Qiskit SDK adapter, state-vector sampler, bit decoder, optional
  dependency/capability and standardized result metadata.
- 1 day: shared exact/Qulacs/Qiskit benchmark case and result methodology.
- 0.5–1 day: API request/capability and focused dashboard backend selector.
- 1–1.5 days: optional-environment validation, docs, regressions and
  cross-platform dependency verification.

This estimate excludes IBM hardware credentials, Runtime execution, persisted
experiment history, cloud deployment and route-specific QAOA modeling.

## 13. Recommended implementation sequence and proposed file plan

1. **Normalize algorithm/circuit semantics.** Refactor
   `src/qsupply/qaoa.py` so shared QAOA instructions describe canonical
   mathematical rotations, not Qulacs signs. Update
   `src/qsupply/backends/qulacs.py` to translate those operations and add
   backend-independent and Qulacs unitary regression tests in
   `tests/test_qaoa.py`.
2. **Add optional Qiskit adapter.** Create
   `src/qsupply/backends/qiskit.py` and keep Qiskit imports lazy. Implement a
   sampler using the current Qiskit 2.x V2 APIs and a deterministic decoder.
   Add `requirements-qiskit.txt`; only add a separate Aer requirement if the
   Aer path is actually implemented and tested. Add
   `tests/test_qiskit_backend.py` with SDK-present tests and missing-package
   tests.
3. **Make cross-solver benchmarking real.** Add a QUBO benchmark-case / runner
   (recommended new `src/qsupply/qubo_benchmarking.py` and
   `tests/test_qubo_benchmarking.py`) that adapts one source problem to each
   solver's declared representation, reports energy/feasibility/samples/timing
   separately, and supports repeated seeds. Avoid changing CVRP benchmarking.
4. **Expose capability and backend selection.** Extend
   `src/qsupply/api/schemas.py` and
   `src/qsupply/api/app.py` for explicit backend ID and accurate capability
   reporting; test in `tests/test_quantum_api.py`. Keep the existing Qulacs
   default request behavior for compatibility or version it deliberately.
5. **Add the minimum UI selector.** Update `frontend/src/App.tsx`,
   `frontend/src/api/client.ts`, generated OpenAPI types, `frontend/src/App.test.tsx`
   and only the relevant CSS. Add a selectable Qiskit option only when the API
   reports it available.
6. **Document and validate.** Update `README.md`, `src/README.md` and
   `examples/README.md`; add `examples/qiskit_qaoa.py` for the same seeded
   synthetic case. Verify both optional environments, all tests, typecheck,
   build and diff checks.

Do not modify QUBO/Ising objective conventions, CVRP solvers, production
configuration, or QARP integration as part of this follow-on milestone.

## 14. Blockers and unresolved decisions

1. **Resolve the shared gate-sign convention first.** A direct Qiskit gate
   translation of the current Qulacs-signed plan is mathematically wrong.
2. **Choose local simulation scope.** This audit recommends Qiskit SDK
   `StatevectorSampler` first. Decide whether Aer is actually needed for the
   initial use case; it adds binary dependencies and is currently in reduced
   maintenance.
3. **Confirm optional dependency policy.** There is no lockfile or packaging
   metadata. Decide whether optional extras remain requirements text files and
   how exact SDK/Aer versions are pinned for reproducible deployments.
4. **Define benchmark budget fields.** Choose whether user-facing “iterations”
   means optimizer updates (current behavior), objective evaluations, or
   circuit executions; report all relevant counts.
5. **Define timeout behavior.** Agree on synchronous request limits versus a
   worker/job model before accepting larger Qiskit/Aer runs.
6. **Define backend identity precisely.** Qiskit local statevector, Qiskit Aer
   statevector/noisy simulation and IBM QPU execution are separate backends and
   must have separate IDs, availability checks and timing labels.
7. **No hardware path is ready.** Qiskit is not installed or configured;
   IBM Runtime credentials, account, backend selection and remote submission
   are not present. This does not block a local simulator adapter, but blocks
   any claim of Qiskit hardware execution.

## Official references checked

- [Qiskit SDK latest API root](https://quantum.cloud.ibm.com/docs/en/api/qiskit/root) — SDK 2.6 documentation.
- [QAOAAnsatz API](https://quantum.cloud.ibm.com/docs/en/api/qiskit/qiskit.circuit.library.QAOAAnsatz) — current parameterized QAOA circuit API.
- [StatevectorSampler API](https://quantum.cloud.ibm.com/docs/en/api/qiskit/qiskit.primitives.StatevectorSampler) — V2 sampler, shots and seed.
- [Local simulation with Qiskit primitives](https://quantum.cloud.ibm.com/docs/en/guides/simulate-with-qiskit-sdk-primitives) — local state-vector sampler/estimator distinction.
- [Qiskit PyPI](https://pypi.org/project/qiskit/) — current 2.6.1 release and Python requirement.
- [Qiskit Aer PyPI](https://pypi.org/project/qiskit-aer/) and [Aer documentation](https://qiskit.github.io/qiskit-aer/) — current 0.18.2 package and simulator scope.
- [Aer V2 sampler guide](https://qiskit.github.io/qiskit-aer/getting_started.html) — `qiskit_aer.primitives.SamplerV2` workflow.
- [Qiskit Optimization PyPI](https://pypi.org/project/qiskit-optimization/) — archived status and unsupported notice.
- [Qiskit Optimization ecosystem compatibility](https://qiskit.github.io/ecosystem/pypi/qiskit-optimization/) — compatibility currently listed through SDK 2.4.1.
- [Qiskit Optimization 0.7 QAOA API](https://qiskit-community.github.io/qiskit-optimization/stubs/qiskit_optimization.minimum_eigensolvers.QAOA.html) — primitive-based algorithm details and its separate package.
