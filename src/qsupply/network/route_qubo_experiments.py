"""Reproducible, local experiments for the finite synthetic route-QUBO models.

The harness reuses QSupply's route formulation, exact solver, classical route
assignment and generic repeated-QAOA benchmark. Exactness is only over the
stored candidate routes; it is not a claim about all routes in the network.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import math
import platform
from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import datetime
from fractions import Fraction
from math import sqrt
from pathlib import Path
from statistics import median
from time import perf_counter
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from ..backends.registry import DEFAULT_QUANTUM_BACKEND_REGISTRY
from ..ising import qubo_to_ising
from ..qaoa import QAOAConfig
from ..quantum_benchmark import benchmark_qaoa_backends_repeated, optimal_feasible_rate
from ..solver import ExactQUBOSolver, ProblemRepresentation
from .global_demo import global_demo_disruptions, global_demo_network, global_demo_shipments
from .planning import ObjectiveWeights, assign_routes, compare_recovery
from .route_qubo import UnsupportedRouteQUBOError, formulate_route_assignment_qubo
from .route_qubo_demo import ROUTE_QUBO_DEMO_SCENARIO


@dataclass(frozen=True)
class RouteExperimentSpec:
    """Deterministic synthetic instance definition, including route-generation cap."""

    problem_id: str
    shipment_ids: tuple[str, ...]
    max_routes_per_shipment: int = 3
    scenario_id: str | None = ROUTE_QUBO_DEMO_SCENARIO.id

    def __post_init__(self) -> None:
        if not self.problem_id or not isinstance(self.problem_id, str):
            raise ValueError("problem_id must be a non-empty string")
        if isinstance(self.shipment_ids, (str, bytes)):
            raise TypeError("shipment_ids must be a sequence of IDs")
        shipment_ids = tuple(self.shipment_ids)
        if not shipment_ids or len(set(shipment_ids)) != len(shipment_ids):
            raise ValueError("shipment_ids must be a non-empty unique sequence")
        if any(not isinstance(item, str) or not item for item in shipment_ids):
            raise ValueError("shipment_ids must contain non-empty strings")
        object.__setattr__(self, "shipment_ids", shipment_ids)
        if isinstance(self.max_routes_per_shipment, bool) or not isinstance(self.max_routes_per_shipment, int):
            raise TypeError("max_routes_per_shipment must be an integer")
        if self.max_routes_per_shipment < 1:
            raise ValueError("max_routes_per_shipment must be positive")
        if self.scenario_id is not None and (not isinstance(self.scenario_id, str) or not self.scenario_id):
            raise ValueError("scenario_id must be a non-empty string or None")


SYNTHETIC_ROUTE_EXPERIMENTS = (
    RouteExperimentSpec("route-qubo-8", ("EXP-104", "EXP-407")),
    RouteExperimentSpec("route-qubo-10", ("EXP-104", "EXP-205", "EXP-306")),
    RouteExperimentSpec("route-qubo-11", ("EXP-104", "EXP-407", "EXP-508")),
    RouteExperimentSpec("route-qubo-12", ("EXP-104", "EXP-205", "EXP-407", "EXP-508"), scenario_id=None),
)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("experiment configuration mapping keys must be strings")
        return MappingProxyType({key: _freeze(v) for key, v in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(v) for v in value)
    if value is None or isinstance(value, (str, bool, int, Fraction)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise TypeError("experiment configuration must contain finite JSON-compatible values")


def _json_value(value: Any) -> Any:
    if isinstance(value, frozenset):
        return sorted(_json_value(item) for item in value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {item.name: _json_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(v) for v in value]
    if isinstance(value, Fraction):
        return {"numerator": value.numerator, "denominator": value.denominator}
    if hasattr(value, "value") and isinstance(value.value, str):
        return value.value
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), default=str)


def _package_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


@dataclass(frozen=True)
class ExperimentConfiguration:
    """Immutable provenance for an instance/profile/backend/seed execution."""

    problem_id: str
    problem_size: int
    qubo_variable_count: int
    objective_profile: str
    candidate_generation: Mapping[str, Any]
    objective_weights: Mapping[str, int]
    penalty_configuration: Mapping[str, Any]
    constant_offset: str
    backend: str
    qaoa: Mapping[str, Any]
    random_seed: int | None
    software_versions: Mapping[str, str | None]
    problem_fingerprint: str
    configuration_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.problem_id, str) or not self.problem_id:
            raise ValueError("problem_id must be non-empty")
        for name in ("problem_size", "qubo_variable_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if not isinstance(self.backend, str) or not self.backend:
            raise ValueError("backend must be non-empty")
        if not isinstance(self.objective_profile, str) or not self.objective_profile:
            raise ValueError("objective_profile must be non-empty")
        if not isinstance(self.constant_offset, str) or not isinstance(self.problem_fingerprint, str):
            raise TypeError("constant_offset and problem_fingerprint must be strings")
        if len(self.problem_fingerprint) != 64 or any(c not in "0123456789abcdef" for c in self.problem_fingerprint):
            raise ValueError("problem_fingerprint must be a lowercase SHA-256 hex digest")
        if self.random_seed is not None and (isinstance(self.random_seed, bool) or not isinstance(self.random_seed, int)):
            raise TypeError("random_seed must be an integer or None")
        map_names = ("candidate_generation", "objective_weights", "penalty_configuration", "qaoa", "software_versions")
        for name in map_names:
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise TypeError(f"{name} must be a mapping")
            object.__setattr__(self, name, _freeze(value))
        payload = {item.name: getattr(self, item.name) for item in fields(self) if item.name != "configuration_id"}
        expected_id = hashlib.sha256(_canonical_json(payload).encode()).hexdigest()
        if self.configuration_id != expected_id:
            raise ValueError("configuration_id does not match the immutable configuration")

    @classmethod
    def create(cls, **fields: Any) -> "ExperimentConfiguration":
        frozen = {key: _freeze(value) for key, value in fields.items()}
        identity = hashlib.sha256(_canonical_json(frozen).encode()).hexdigest()
        return cls(**frozen, configuration_id=identity)

    def to_dict(self) -> dict[str, Any]:
        return {item.name: _json_value(getattr(self, item.name)) for item in fields(self)}


@dataclass(frozen=True)
class ExperimentRun:
    """One independently validated solver result; unavailable metrics stay null."""

    configuration: ExperimentConfiguration
    solver: str
    status: str
    feasible: bool | None
    assignment: Mapping[str, int] | None
    selected_routes: Mapping[str, str] | None
    qubo_energy: str | None
    ising_energy: str | None
    constant_offset: str
    full_penalized_energy: str | None
    business_objective: str | None
    optimal_feasible_gap_percent: float | None
    violations: tuple[str, ...]
    execution_time_seconds: float | None
    timing_scope: str
    backend_metadata: Mapping[str, Any] | None
    domain_fingerprint: str | None = None
    qubo_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {item.name: _json_value(getattr(self, item.name)) for item in fields(self)}


@dataclass(frozen=True)
class RouteExperimentReport:
    manifest: Mapping[str, Any]
    runs: tuple[ExperimentRun, ...]
    summaries: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {"manifest": _json_value(self.manifest), "runs": [r.to_dict() for r in self.runs],
                "summaries": _json_value(self.summaries)}


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _gap(value: Any, reference: Any) -> float | None:
    if value is None or reference is None or reference == 0:
        return None
    return float((value - reference) / abs(reference) * 100)


def _aggregate_runs(runs: Sequence[ExperimentRun]) -> tuple[Mapping[str, Any], ...]:
    groups: dict[tuple[str, str, str], list[ExperimentRun]] = {}
    for run in runs:
        profile = run.configuration.objective_profile
        groups.setdefault((run.configuration.problem_id, profile, run.solver), []).append(run)
    references = {
        (r.configuration.problem_id, r.configuration.objective_profile): Fraction(r.business_objective)
        for r in runs if r.solver == "exact-qubo" and r.status == "completed"
        and r.feasible is True and r.business_objective is not None
    }
    result: list[Mapping[str, Any]] = []
    for (problem_id, profile, solver), records in groups.items():
        energies = [Fraction(run.full_penalized_energy) for run in records if run.full_penalized_energy is not None]
        objectives = [Fraction(run.business_objective) for run in records if run.business_objective is not None]
        evaluated = [run.feasible for run in records if run.feasible is not None]
        times = [run.execution_time_seconds for run in records if run.execution_time_seconds is not None]
        reference = references.get((problem_id, profile))
        success_probability = optimal_feasible_rate(reference, [
            ((run.backend_metadata or {}).get("seed_applied"),
             run.status == "completed" and run.feasible is True,
             Fraction(run.business_objective) if run.business_objective is not None else None)
            for run in records
        ])
        energy_mean = sum(energies, Fraction(0)) / len(energies) if energies else None
        objective_mean = sum(objectives, Fraction(0)) / len(objectives) if objectives else None
        energy_variance = (sum(((value - energy_mean) ** 2 for value in energies), Fraction(0)) / len(energies)
                           if energies and energy_mean is not None else None)
        objective_variance = (sum(((value - objective_mean) ** 2 for value in objectives), Fraction(0)) / len(objectives)
                              if objectives and objective_mean is not None else None)
        result.append(MappingProxyType({
            "summary_kind": "experiment_group", "problem_id": problem_id,
            "domain_fingerprint": records[0].domain_fingerprint,
            "qubo_fingerprint": records[0].qubo_fingerprint,
            "profile": profile, "solver": solver, "run_count": len(records),
            "energy_count": len(energies), "best_full_energy": str(min(energies)) if energies else None,
            "worst_full_energy": str(max(energies)) if energies else None,
            "mean_full_energy_exact": str(energy_mean) if energy_mean is not None else None,
            "median_full_energy_exact": str(median(energies)) if energies else None,
            "energy_variance_exact": str(energy_variance) if energy_variance is not None else None,
            "energy_standard_deviation": sqrt(float(energy_variance)) if energy_variance is not None else None,
            "objective_count": len(objectives),
            "best_business_objective": str(min(objectives)) if objectives else None,
            "worst_business_objective": str(max(objectives)) if objectives else None,
            "mean_business_objective_exact": str(objective_mean) if objective_mean is not None else None,
            "median_business_objective_exact": str(median(objectives)) if objectives else None,
            "business_objective_variance_exact": str(objective_variance) if objective_variance is not None else None,
            "business_objective_standard_deviation": sqrt(float(objective_variance)) if objective_variance is not None else None,
            "feasibility_evaluated_run_count": len(evaluated),
            "feasibility_rate": sum(evaluated) / len(evaluated) if evaluated else None,
            "optimal_feasible_success_probability": success_probability,
            "per_run_execution_times_seconds": tuple(times),
            "aggregate_execution_time_seconds": sum(times) if times else None,
        }))
    return tuple(result)


def prepare_route_candidates(spec: RouteExperimentSpec, weights: ObjectiveWeights):
    """Generate the same fixed candidate set for bounded and classical-only cases."""
    all_profiles = {p.request.id: p for p in global_demo_shipments()}
    missing = set(spec.shipment_ids) - set(all_profiles)
    if missing:
        raise ValueError(f"unknown synthetic shipment IDs: {sorted(missing)}")
    profiles = tuple(all_profiles[key] for key in spec.shipment_ids)
    scenarios = {s.id: s for s in (*global_demo_disruptions(), ROUTE_QUBO_DEMO_SCENARIO)}
    scenario = scenarios.get(spec.scenario_id)
    if spec.scenario_id is not None and scenario is None:
        raise ValueError("only declared deterministic scenarios are supported")
    comparison = compare_recovery(global_demo_network(), profiles, scenario, weights,
                                  max_routes=spec.max_routes_per_shipment)
    return profiles, scenario, comparison


def _digest(value):
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def source_revision():
    """Content revision works in a checkout, a dirty tree and an unpacked release."""
    package = Path(__file__).resolve().parents[1]
    files = {path.relative_to(package).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in package.rglob("*.py")}
    return "sha256:" + _digest(files)


def identified_route_problem(spec, weights):
    profiles, scenario, comparison = prepare_route_candidates(spec, weights)
    network = global_demo_network()
    domain_id = _digest({
        "schema": "qsupply-route-domain-v1", "spec": spec, "network": network,
        "shipments": profiles, "disruption": scenario, "weights": weights,
        "references": comparison.normalization_references,
        "candidates": comparison.recovery_candidates,
    })
    try:
        formulation = formulate_route_assignment_qubo(
            network, profiles, comparison.recovery_candidates, weights,
            comparison.normalization_references, scenario,
        )
    except UnsupportedRouteQUBOError as error:
        error.domain_fingerprint = domain_id
        raise
    qubo_id = _digest({
        "schema": "qsupply-route-qubo-v1", "variables": formulation.variable_order,
        "offset": str(formulation.offset), "coefficients": [
            (i, j, str(v)) for (i, j), v in sorted(formulation.qubo.coefficients.items())
        ],
    })
    return formulation, comparison, domain_id, qubo_id


def _problem(spec, weights):
    formulation, comparison, _, _ = identified_route_problem(spec, weights)
    return formulation, comparison


def run_route_experiments(
    *, specs: Sequence[RouteExperimentSpec] = SYNTHETIC_ROUTE_EXPERIMENTS,
    weights_by_profile: Mapping[str, ObjectiveWeights] | None = None,
    backends: Sequence[str] = ("qiskit", "qulacs"),
    seeds: Sequence[int] = (11, 22, 33),
    depth: int = 1,
    optimizer: str = "spsa",
    iterations: int = 2,
    shots: int = 64,
    registry: Any = None,
    stop_backend_on_failure: bool = False,
) -> RouteExperimentReport:
    """Run identical finite route problems through exact, classical and selected QAOA solvers.

    A named but unavailable backend yields explicit unavailable rows. It is never
    replaced by another solver. Unknown backend identifiers raise ValueError.
    """
    if not seeds or len(set(seeds)) != len(seeds) or any(isinstance(s, bool) or not isinstance(s, int) for s in seeds):
        raise ValueError("seeds must be distinct explicit integers")
    if len(set(backends)) != len(backends):
        raise ValueError("backend identifiers must be unique")
    # Validate the requested QAOA settings before any problem work, even when
    # an optional backend is absent. Unsupported requests never become fake
    # "unavailable" outcomes.
    QAOAConfig(depth=depth, optimizer=optimizer, max_iterations=iterations,
               shots=shots, random_seed=seeds[0])
    backend_registry = registry or DEFAULT_QUANTUM_BACKEND_REGISTRY
    registrations = {backend: backend_registry.get(backend) for backend in backends}
    for registration in registrations.values():
        for seed in seeds:
            errors = registration.configuration_errors({
                "depth": depth, "optimizer": optimizer, "max_iterations": iterations,
                "shots": shots, "random_seed": seed,
            })
            if errors:
                raise ValueError(f"unsupported configuration for {registration.backend_id}: {'; '.join(errors)}")
    profiles_weights = weights_by_profile or {
        "balanced": ObjectiveWeights(),
        "carbon-priority": ObjectiveWeights(cost=0, delivery_time=0, carbon=100, resilience=0),
    }
    result_runs: list[ExperimentRun] = []
    summaries: list[Mapping[str, Any]] = []
    manifest_problems: list[dict[str, Any]] = []
    revision = source_revision()
    for spec in specs:
        for profile_name, weights in profiles_weights.items():
            formulation, comparison, domain_id, qubo_id = identified_route_problem(spec, weights)
            request = formulation.solver_request(ProblemRepresentation.QUBO)
            fingerprint_payload = {
                "spec": asdict(spec), "weights": asdict(weights),
                "references": asdict(comparison.normalization_references),
                "variable_order": formulation.variable_order,
                "qubo": {"variables": formulation.qubo.variables,
                         "coefficients": [(i, j, str(v)) for (i, j), v in formulation.qubo.coefficients.items()]},
                "offset": str(formulation.offset),
                "candidate_routes": {sid: [r.id for r in routes] for sid, routes in formulation.candidates.items()},
                "candidate_route_details": {sid: [{"id": r.id, "freight_cost": str(r.freight_cost),
                    "transit_time": str(r.transit_time), "carbon_kg": str(r.carbon_kg),
                    "resilience_exposure": str(r.resilience_exposure),
                    "legs": [(leg.link_id, leg.mode.value, leg.origin_id, leg.destination_id)
                             for leg in r.legs]} for r in routes]
                    for sid, routes in formulation.candidates.items()},
                "shipment_inputs": [{"id": p.request.id, "origin": p.request.origin_id,
                    "destination": p.request.destination_id, "quantity": p.request.quantity,
                    "quantity_unit": p.request.quantity_unit, "deadline": p.request.deadline,
                    "priority": p.priority, "delay_penalty_per_day": str(p.delay_penalty_per_day),
                    "maximum_transit_time": p.maximum_transit_time}
                    for p in formulation.profiles],
                "effective_capacities": dict(formulation.effective_capacities),
            }
            fingerprint = hashlib.sha256(_canonical_json(fingerprint_payload).encode()).hexdigest()
            exact_started = perf_counter()
            exact = ExactQUBOSolver().solve(request)
            exact_seconds = perf_counter() - exact_started
            exact_feasible = exact.feasible is True
            exact_evaluation = formulation.evaluate_assignment(exact.best_binary_assignment or {})
            ising = qubo_to_ising(formulation.qubo, offset=formulation.offset)
            exact_ising = ising.energy({k: 1 - 2 * v for k, v in (exact.best_binary_assignment or {}).items()})
            if exact_evaluation.full_penalized_energy != exact.full_energy or exact_ising != exact.full_energy:
                raise ArithmeticError("exact reference failed independent QUBO/Ising/full-energy reconciliation")
            exact_business = exact_evaluation.business_metrics.weighted_objective if exact_feasible and exact_evaluation.business_metrics else None
            base_config = dict(problem_id=spec.problem_id, problem_size=len(spec.shipment_ids),
                               qubo_variable_count=formulation.variable_count,
                               objective_profile=profile_name,
                               candidate_generation={"shipment_ids": spec.shipment_ids,
                                   "max_routes_per_shipment": spec.max_routes_per_shipment,
                                   "scenario_id": spec.scenario_id,
                                   "candidate_counts": {k: len(v) for k,v in formulation.candidates.items()},
                                   "decision_variables": formulation.decision_variable_count,
                                   "slack_variables": formulation.slack_variable_count,
                                   "one_hot_constraints": len(formulation.profiles),
                                   "capacity_constraints": len(formulation.capacity_encodings),
                                   "constraint_count": len(formulation.profiles) + len(formulation.capacity_encodings),
                                   "fixed_normalization_references": asdict(comparison.normalization_references)},
                               objective_weights=asdict(weights),
                               penalty_configuration={"method": "formulation-derived feasible-objective upper bound plus one",
                                                     "penalty": str(formulation.penalty)},
                               constant_offset=str(formulation.offset),
                               software_versions={"python": platform.python_version(),
                                   "qsupply": revision, "qiskit": _package_version("qiskit"),
                                   "qulacs": _package_version("qulacs")},
                               problem_fingerprint=fingerprint)
            def config_for(backend: str, seed: int | None) -> ExperimentConfiguration:
                return ExperimentConfiguration.create(**base_config, backend=backend,
                    qaoa={"depth": depth, "optimizer": optimizer, "iterations": iterations, "shots": shots},
                    random_seed=seed)
            def make_run(backend: str, status: str, assignment: Mapping[str, int] | None,
                         elapsed: float | None, timing: str, metadata: Mapping[str, Any] | None,
                         seed: int | None) -> ExperimentRun:
                if assignment is None:
                    return ExperimentRun(config_for(backend, seed), backend, status, False if status == "infeasible" else None, None, None,
                        None, None, str(formulation.offset), None, None, None, (), elapsed, timing,
                        _freeze(metadata) if metadata else None,
                        domain_fingerprint=domain_id, qubo_fingerprint=qubo_id)
                evaluation = formulation.evaluate_assignment(assignment)
                spins = {k: 1 - 2 * v for k, v in assignment.items()}
                ising_energy = ising.energy(spins)
                if ising_energy != evaluation.full_penalized_energy:
                    raise ArithmeticError("sample QUBO/Ising/full energy mismatch")
                feasible = evaluation.feasibility.feasible
                selected = dict(evaluation.feasibility.selected_routes) if feasible else None
                business = evaluation.business_metrics.weighted_objective if feasible and evaluation.business_metrics else None
                violations = evaluation.feasibility.violations
                return ExperimentRun(config_for(backend, seed), backend, status, feasible,
                    _freeze(dict(assignment)), _freeze(selected) if selected else None,
                    str(evaluation.qubo_energy), str(ising_energy), str(formulation.offset),
                    str(evaluation.full_penalized_energy), _text(business),
                    _gap(business, exact_business) if feasible else None, violations,
                    elapsed, timing, _freeze(metadata) if metadata else None,
                        domain_fingerprint=domain_id, qubo_fingerprint=qubo_id)
            exact_routes = dict(exact_evaluation.feasibility.selected_routes) if exact_feasible else None
            result_runs.append(make_run("exact-qubo", "completed", exact.best_binary_assignment,
                exact_seconds, "exact solver call wall time; excludes formulation and validation",
                {"scope": "exhaustive binary assignment enumeration", "enumerated_assignments": 1 << formulation.variable_count}, None))
            classical_started = perf_counter()
            classical = assign_routes(formulation.network, formulation.profiles, formulation.candidates,
                formulation.weights, formulation.normalization_references, formulation.scenario)
            classical_seconds = perf_counter() - classical_started
            if classical is None:
                result_runs.append(make_run("classical-assignment", "infeasible", None, classical_seconds,
                    "assign_routes call wall time", {"method": "joint candidate assignment search"}, None))
            else:
                route_ids = {sid: route.id for sid, route in classical.routes.items()}
                assignment = formulation.encode_plan(route_ids)
                result_runs.append(make_run("classical-assignment", "completed", assignment, classical_seconds,
                    "assign_routes call wall time; includes its feasibility checks", {"method": classical.method}, None))
            manifest_problems.append({"problem_id": spec.problem_id, "profile": profile_name,
                "domain_fingerprint": domain_id, "qubo_fingerprint": qubo_id,
                "fingerprint": fingerprint, "shipments": len(spec.shipment_ids),
                "candidate_routes": sum(len(v) for v in formulation.candidates.values()),
                "variables": formulation.variable_count, "decision_variables": formulation.decision_variable_count,
                "slack_variables": formulation.slack_variable_count,
                "capacity_constraints": len(formulation.capacity_encodings),
                "one_hot_constraints": len(formulation.profiles),
                "constraint_count": len(formulation.profiles) + len(formulation.capacity_encodings),
                "objective_weights": asdict(weights),
                "candidate_generation": {"max_routes_per_shipment": spec.max_routes_per_shipment,
                    "scenario_id": spec.scenario_id,
                    "candidate_counts": {key: len(value) for key, value in formulation.candidates.items()},
                    "fixed_normalization_references": asdict(comparison.normalization_references)},
                "penalty_configuration": {"method": "formulation-derived feasible-objective upper bound plus one",
                    "penalty": str(formulation.penalty)},
                "software_versions": {"python": platform.python_version(), "qsupply": revision,
                    "qiskit": _package_version("qiskit"), "qulacs": _package_version("qulacs")},
                "constant_offset": str(formulation.offset),
                "exact_penalized_minimum_feasible": exact_feasible,
                "exact_best_feasible_objective": _text(exact_business),
                "exact_routes": exact_routes, "qubo_penalty": str(formulation.penalty), "offset": str(formulation.offset)})
            for backend, registration in registrations.items():
                if not registration.availability_check():
                    for seed in seeds:
                        result_runs.append(make_run(backend, "unavailable", None, None,
                            "not measured", {"reason": "registered optional backend is unavailable", "version": registration.version_check()}, seed))
                    continue
                try:
                    solver = registration.solver_factory(QAOAConfig(depth=depth, optimizer=optimizer,
                        max_iterations=iterations, shots=shots, random_seed=seeds[0]))
                except Exception as error:
                    for seed in seeds:
                        result_runs.append(make_run(backend, "not_run", None, None, "solver setup failed",
                            {"error_type": type(error).__name__, "error": str(error)}, seed))
                    continue
                report = benchmark_qaoa_backends_repeated(
                    f"{spec.problem_id}:{profile_name}", request, (solver,), seeds=seeds,
                    record_backend_exceptions=True, stop_backend_on_failure=stop_backend_on_failure,
                )
                for record in report.runs:
                    if record.best_binary_assignment is None:
                        result_runs.append(make_run(backend, record.status, None, record.execution_time_seconds,
                            record.timing_scope, record.execution_metadata, record.requested_seed))
                    else:
                        result_runs.append(make_run(backend, record.status, record.best_binary_assignment,
                            record.execution_time_seconds, record.timing_scope,
                            {"execution": record.execution_metadata, "backend_version": record.backend_version,
                             "seed_applied": record.seed_applied, "requested_seed": record.requested_seed,
                             "shots": record.shots, "depth": record.qaoa_depth,
                             "circuit_depth": record.circuit_depth,
                             "optimizer_evaluations": record.optimizer_evaluations,
                             "sample_call_seconds": record.circuit_execution_time_seconds,
                             "feasible_sample_fraction": record.feasible_sample_fraction,
                             "optimal_feasible_success_probability": next((s.optimal_feasible_success_probability for s in report.summaries), None)},
                            record.requested_seed))
                summaries.extend({"problem_id": spec.problem_id, "profile": profile_name,
                    "solver_id": summary.solver_id, "run_count": summary.run_count,
                    "feasibility_rate": summary.feasibility_rate,
                    "optimal_feasible_success_probability": summary.optimal_feasible_success_probability,
                    "energy_statistics": asdict(summary.full_energy_statistics),
                    "business_objective_statistics": asdict(summary.business_objective_statistics),
                    "per_run_execution_times_seconds": summary.per_run_execution_times_seconds,
                    "aggregate_execution_time_seconds": summary.aggregate_execution_time_seconds,
                    "timing_scope": summary.timing_scope} for summary in report.summaries)
    manifest = {"schema_version": 1, "synthetic": True, "methodology":
        "All methods use identical generated route candidates, fixed baseline normalization, business objective and independent validator. Exact minima are over the finite QUBO variable space only.",
        "stop_backend_on_failure": stop_backend_on_failure,
        "requested_seeds": tuple(seeds), "qaoa_configuration": {"depth": depth,
            "optimizer": optimizer, "iterations": iterations, "shots": shots},
        "instances": tuple(manifest_problems),
        "backend_availability": {key: {"available": reg.availability_check(), "version": reg.version_check(),
           "execution_mode": reg.execution_mode.value} for key, reg in registrations.items()}}
    summaries.extend(_aggregate_runs(result_runs))
    return RouteExperimentReport(_freeze(manifest), tuple(result_runs), tuple(_freeze(x) for x in summaries))


def export_experiment_report(report: RouteExperimentReport, directory: str | Path, *, overwrite: bool = False) -> tuple[Path, Path, Path]:
    """Write manifest, individual runs and summary CSV without overwriting by default."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    paths = (target / "manifest.json", target / "runs.json", target / "summary.csv")
    if not overwrite and any(path.exists() for path in paths):
        raise FileExistsError("experiment export exists; choose a new directory or set overwrite=True")
    with paths[0].open("w", encoding="utf-8") as stream:
        json.dump(_json_value(report.manifest), stream, indent=2, sort_keys=True)
    with paths[1].open("w", encoding="utf-8") as stream:
        json.dump([run.to_dict() for run in report.runs], stream, indent=2, sort_keys=True)
    fields = ("problem_id", "profile", "domain_fingerprint", "qubo_fingerprint", "solver", "run_count", "energy_count",
              "best_full_energy", "worst_full_energy", "mean_full_energy_exact",
              "median_full_energy_exact", "energy_variance_exact", "energy_standard_deviation", "objective_count",
              "best_business_objective", "worst_business_objective",
              "mean_business_objective_exact", "median_business_objective_exact",
              "business_objective_variance_exact", "business_objective_standard_deviation", "feasibility_evaluated_run_count",
              "feasibility_rate", "optimal_feasible_success_probability",
              "per_run_execution_times_seconds", "aggregate_execution_time_seconds")
    with paths[2].open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for summary in report.summaries:
            if summary.get("summary_kind") != "experiment_group":
                continue
            row = {key: summary.get(key) for key in fields}
            if row["per_run_execution_times_seconds"] is not None:
                row["per_run_execution_times_seconds"] = json.dumps(row["per_run_execution_times_seconds"])
            writer.writerow(row)
    return paths
