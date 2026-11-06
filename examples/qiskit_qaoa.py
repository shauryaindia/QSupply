"""Compare exact, Qulacs and Qiskit solvers on the same synthetic QUBO."""

from __future__ import annotations

from qsupply import QAOAConfig, SolverRequest
from qsupply.backends.qiskit import QiskitBackend, QiskitQAOASolver
from qsupply.backends.qulacs import QulacsBackend, QulacsQAOASolver
from qsupply.import_export import (
    evaluate_business_objective,
    formulate_import_export_qubo,
    synthetic_import_export_problem,
)
from qsupply.quantum_benchmark import benchmark_qaoa_backends


def main() -> None:
    problem = synthetic_import_export_problem()
    formulation = formulate_import_export_qubo(problem)
    request = SolverRequest(
        qubo=formulation.qubo,
        constant_offset=formulation.offset,
        validator=formulation.check_feasibility,
        decoder=formulation.decode,
        business_objective=lambda choices: evaluate_business_objective(problem, choices),
        random_seed=2026,
        configuration={"problem_id": "synthetic-import-export-5-variable"},
    )
    config = QAOAConfig(
        depth=1,
        optimizer="coordinate",
        max_iterations=1,
        shots=128,
        random_seed=2026,
    )
    solvers = []
    if QulacsBackend.is_available():
        solvers.append(QulacsQAOASolver(config))
    if QiskitBackend.is_available():
        solvers.append(QiskitQAOASolver(config))
    if not solvers:
        raise SystemExit(
            "Install at least one optional simulator using requirements-quantum.txt "
            "or requirements-qiskit.txt."
        )

    records = benchmark_qaoa_backends(
        "synthetic-import-export-5-variable", request, solvers
    )
    print("Synthetic import-export QUBO benchmark (single local timing observations)")
    print(f"QUBO variables: {len(formulation.qubo.variables)}; exact assignments: 32")
    for record in records:
        print(
            f"{record.solver_id}: status={record.status}, energy={record.best_sampled_energy}, "
            f"exact={record.exact_optimum}, gap={record.relative_energy_gap_percent}, "
            f"feasible={record.best_sample_feasible}, objective={record.business_objective}, "
            f"time={record.execution_time_seconds:.6f}s, mode={record.execution_mode}, "
            f"backend={record.backend_name}"
        )


if __name__ == "__main__":
    main()
