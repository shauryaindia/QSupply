"""Run bounded QAOA on the synthetic import-export QUBO using Qulacs."""

from qsupply import (
    ExactQUBOSolver,
    ProblemRepresentation,
    QAOAConfig,
    SolverRequest,
    evaluate_business_objective,
    formulate_import_export_qubo,
    synthetic_import_export_problem,
)
from qsupply.backends.qulacs import QulacsBackend, QulacsQAOASolver


def main() -> None:
    if not QulacsBackend.is_available():
        raise SystemExit(
            "Qulacs is optional. Install it with `python3 -m pip install "
            "-r requirements-quantum.txt`."
        )

    problem = synthetic_import_export_problem()
    formulation = formulate_import_export_qubo(problem)
    request = SolverRequest(
        qubo=formulation.qubo,
        constant_offset=formulation.offset,
        representation=ProblemRepresentation.ISING,
        validator=formulation.check_feasibility,
        decoder=formulation.decode,
        business_objective=lambda selected: evaluate_business_objective(
            problem, selected
        ),
        random_seed=101,
        configuration={"example": "synthetic-import-export"},
    )
    config = QAOAConfig(
        depth=1,
        optimizer="spsa",
        max_iterations=2,
        shots=64,
        random_seed=101,
    )
    result = QulacsQAOASolver(config).solve(request)
    exact = ExactQUBOSolver().solve(
        SolverRequest(
            qubo=formulation.qubo,
            constant_offset=formulation.offset,
            validator=formulation.check_feasibility,
            decoder=formulation.decode,
            business_objective=lambda selected: evaluate_business_objective(
                problem, selected
            ),
        )
    )

    print(f"Backend: {result.backend_name} {result.backend_version}")
    print(f"Algorithm: {result.algorithm_name}, p={result.circuit_depth}")
    print(f"Variables: {len(result.variable_order)} ({', '.join(result.variable_order)})")
    print(f"Seed: {result.random_seed}; total measurements: {result.sample_count}")
    print(f"QAOA best full energy: {result.full_energy}")
    print(f"Exact reference full energy: {exact.full_energy}")
    print(f"Final sample feasible fraction: {result.feasible_sample_rate:.3f}")
    print(f"Best sample feasible: {result.feasible}")
    if result.decoded_solution is not None:
        print(f"Decoded plan: {dict(result.decoded_solution)}")
        print(f"Business objective: {result.business_objective}")
    if result.error:
        raise SystemExit(result.error)


if __name__ == "__main__":
    main()
