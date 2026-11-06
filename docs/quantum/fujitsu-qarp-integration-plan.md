# Fujitsu QARP integration plan for FX700

## Status

This is a design and readiness document only. QSupply has no QARP adapter, no
QARP package in the repository, and no verified FX700 connection. The
confidential package must be supplied through the challenge-approved channel;
it must not be fetched, copied into this repository, or redistributed.

The milestone request provided these FX700 setup requirements: Python
3.12.10 managed with `pyenv`, a dedicated virtual environment, manual
installation/copying of the challenge-supplied QARP package, Fujitsu-provided
requirements, and Slurm interactive or batch execution. The referenced setup
guide file itself was not available in the repository or accessible local
attachment paths during implementation, so those details have not been
independently checked against the guide.

## Proposed adapter boundary

Keep the shared QSupply path:

`domain problem -> QUBO + offset -> IsingModel -> SolverRequest -> adapter -> samples -> independent decoder/validator`

When official QARP documentation and the approved package are available, add
an isolated `qsupply.backends.fujitsu_qarp` adapter. It should implement the
existing backend sampling/solver boundary and translate QSupply's declared
variable order into the QARP qubit/register order exactly once. It should not
reimplement QUBO conversion, the QAOA parameter optimizer, domain decoding,
or feasibility validation. Keep QARP imports lazy so ordinary QSupply use
does not require the proprietary package.

The adapter should return raw counts/samples plus execution metadata. QSupply
must then map those bits back to its variable order and independently compute
QUBO energy, full energy including the preserved offset, Ising energy,
feasibility, and business metrics.

## Assumptions requiring verification

Before writing the adapter, verify against the actual package and official
documentation:

- Supported QARP Python modules, constructors, methods, and version.
- Whether it accepts QUBO, Ising, Pauli operators, circuits, or another format.
- Its binary/spin convention, coefficient orientation, constant-offset support,
  register ordering, and returned bitstring convention.
- QAOA circuit and parameter APIs, supported mixer/state preparation, and
  whether parameter optimization belongs in QARP or remains in QSupply.
- Submission method, result/polling API, measurement format, and job identifiers.
- Which operations run inside a Slurm allocation and which, if any, are
  available from an interactive session.
- Supported Python, numerical libraries, compiler/runtime requirements,
  package installation layout, and environment activation procedure.
- Whether the challenge permits transmitting the synthetic problem and
  associated benchmark outputs to the target environment.

Do not infer an API from the Qiskit, Qulacs, or generic quantum SDKs.

## FX700 environment setup (after access is approved)

1. Confirm host/alias, username, port, approved authentication method, and
   network/static-IP requirements with the challenge administrator. Keep
   private keys outside the repository and do not print credentials.
2. Establish a read-only SSH session first. Confirm host identity and access
   scope; do not change the host environment during this check.
3. Verify `pyenv` and Python 3.12.10, then create the project-specific virtual
   environment using the Fujitsu-provided setup instructions.
4. Install only the supplied requirements and package by the authorized manual
   procedure. Record package versions and checksums without publishing the
   proprietary package.
5. Inspect and run the vendor's smallest supported example inside the
   appropriate Slurm interactive allocation. Do not submit QSupply jobs until
   the SDK example and resource requirements are understood.
6. Capture sanitized runtime/version details and a successful sample retrieval
   for adapter development. Never include credentials, keys, private package
   contents, or confidential challenge procedures in Git.

## Initial verification plan

Start with a tiny, non-sensitive Ising model whose full state space can be
enumerated locally. Verify (a) an explicitly documented known QARP example,
(b) variable/qubit ordering, (c) one sampled assignment and its exact QSupply
energy, and (d) energy and feasibility recomputation in QSupply. Then compare
QARP samples against exact enumeration and the local Qiskit/Qulacs simulators
using identical QUBO coefficients, constant offset, domain constraints, and
business objective. Do not require equal finite-shot histograms unless
sampling configurations make that comparison statistically justified.

## Challenge benchmark plan

After API compatibility and allocation limits are confirmed, run the approved
synthetic five-variable import-export case first, followed by small controlled
instances that vary shipment count and constraint density. Preserve the same
candidate options, objective coefficients, penalty model, constant offset,
seed where supported, QAOA depth, shot budget, and validator across methods.
Report exact optimum, best sampled full energy, energy gap, feasible-sample
fraction, best-sample feasibility, business objective, optimizer settings,
Slurm allocation, queue/wall times, and backend-reported execution time
separately. Label state-vector simulation and QARP execution as different
execution modes. Repeat runs before drawing performance conclusions; never
claim quantum advantage from synthetic or small simulator runs.

## Current blockers

- No FX700 host/connection details or approved access procedure have been
  provided in this task, and remote login was explicitly out of scope.
- No QARP package or authoritative API documentation is present locally.
- Slurm partition, allocation, runtime, memory/qubit limits, and challenge
  submission policy are unverified.
- Package/Python/driver compatibility and measurement semantics are unknown
  until tested on the FX700 environment.

No QARP compatibility or challenge-environment execution is claimed.
