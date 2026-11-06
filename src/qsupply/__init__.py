"""Core optimization models for QSupply."""

from .qubo import QUBO
from .ising import IsingModel, qubo_to_ising
from .solver import (
    BackendType,
    ExactQUBOSolver,
    ExecutionStatus,
    ProblemRepresentation,
    Solver,
    SolverBenchmarkRecord,
    SolverMetadata,
    SolverRequest,
    SolverResult,
    benchmark_solvers,
)
from .qaoa import (
    CircuitOperation,
    QAOAConfig,
    QAOAExecution,
    SampleBatch,
    build_qaoa_circuit_plan,
    run_qaoa,
)
from .import_export import (
    FeasibilityReport,
    ImportExportEvaluation,
    ImportExportFormulation,
    ImportExportProblem,
    Shipment,
    TransportOption,
    evaluate_business_objective,
    formulate_import_export_qubo,
    synthetic_import_export_problem,
)
from .routing import CVRPProblem
from .routing_heuristics import NearestNeighborTwoOptSolver, RouteOptimizationResult
from .exact_routing import (
    ExactCVRPSolution,
    ExactCVRPSolver,
    InfeasibleCVRPError,
    MAX_EXACT_CUSTOMERS,
)
from .benchmarking import (
    BenchmarkMethodResult,
    CVRPBenchmarkReport,
    benchmark_cvrp,
    benchmark_suite,
    generate_synthetic_cvrp,
    synthetic_benchmark_suite,
)

__all__ = [
    "QUBO",
    "IsingModel",
    "qubo_to_ising",
    "BackendType",
    "ProblemRepresentation",
    "ExecutionStatus",
    "SolverMetadata",
    "SolverRequest",
    "SolverResult",
    "SolverBenchmarkRecord",
    "Solver",
    "ExactQUBOSolver",
    "benchmark_solvers",
    "QAOAConfig",
    "CircuitOperation",
    "SampleBatch",
    "QAOAExecution",
    "build_qaoa_circuit_plan",
    "run_qaoa",
    "TransportOption",
    "Shipment",
    "ImportExportProblem",
    "ImportExportFormulation",
    "ImportExportEvaluation",
    "FeasibilityReport",
    "formulate_import_export_qubo",
    "evaluate_business_objective",
    "synthetic_import_export_problem",
    "CVRPProblem",
    "NearestNeighborTwoOptSolver",
    "RouteOptimizationResult",
    "ExactCVRPSolution",
    "ExactCVRPSolver",
    "InfeasibleCVRPError",
    "MAX_EXACT_CUSTOMERS",
    "BenchmarkMethodResult",
    "CVRPBenchmarkReport",
    "benchmark_cvrp",
    "benchmark_suite",
    "generate_synthetic_cvrp",
    "synthetic_benchmark_suite",
]
