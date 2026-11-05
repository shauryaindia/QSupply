"""Exhaustively verify a tiny synthetic import-export QUBO formulation."""

from itertools import product

from qsupply import formulate_import_export_qubo, synthetic_import_export_problem


problem = synthetic_import_export_problem()
formulation = formulate_import_export_qubo(problem)
feasible_assignments = []
for bits in product((0, 1), repeat=len(formulation.qubo.variables)):
    assignment = dict(zip(formulation.qubo.variables, bits))
    if formulation.check_feasibility(assignment).feasible:
        feasible_assignments.append(assignment)

best = min(feasible_assignments, key=formulation.full_energy)
plan = formulation.decode(best)
evaluation = formulation.evaluate(best)

print("Tiny import-export QUBO demonstration (exhaustive enumeration)")
print(f"Penalty coefficient: {formulation.penalty}")
print(f"Constant offset: {formulation.offset}")
print(f"Selected options: {dict(plan)}")
print(f"Business cost: {evaluation.business_cost}")
print(f"Penalty contribution: {evaluation.penalty_contribution}")
print(f"Offset-free QUBO energy: {evaluation.qubo_energy}")
print(f"Full penalized energy: {evaluation.full_penalized_energy}")
