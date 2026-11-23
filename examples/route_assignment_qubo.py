"""Run the bounded synthetic multimodal route-assignment QUBO example."""

from qsupply.network import ObjectiveWeights
from qsupply.network.route_qubo_demo import compare_route_qubo_to_classical


def display(value):
    return f"{float(value):.6f}"


def show(title, result):
    formulation = result.formulation
    print(title)
    print(f"  variables: {formulation.decision_variable_count} route + "
          f"{formulation.slack_variable_count} capacity slack = {formulation.variable_count}")
    print(f"  offset: {display(formulation.offset)}")
    print(f"  full energy: {display(result.exact_result.full_energy)}")
    print(f"  QUBO energy: {display(result.exact_result.qubo_energy)}")
    print(f"  objective: {display(result.exact_result.business_objective)}")
    print(f"  feasible: {result.exact_result.feasible}")
    print(f"  matches classical candidate assignment: {result.same_objective}")
    for shipment, route in result.exact_result.decoded_solution.items():
        candidate = next(item for item in formulation.candidates[shipment] if item.id == route)
        locations = " → ".join(candidate.location_ids)
        modes = " → ".join(mode.value for mode in candidate.modes)
        print(f"  {shipment}: {locations} [{modes}]")


def main():
    balanced = compare_route_qubo_to_classical(ObjectiveWeights())
    print("Synthetic route QUBO; Shanghai port-road capacity reduced to 3 load units")
    print("Exactness is limited to the generated three-route candidate set per shipment.")
    print("The classical result is enumerated over that same candidate set.\n")
    print("Undisrupted classical baseline:")
    for shipment, candidate in balanced.candidate_comparison.baseline.routes.items():
        print(f"  {shipment}: {' → '.join(candidate.location_ids)}")
    print()
    show("Balanced objective (40/25/20/15)", balanced)

    carbon_priority = compare_route_qubo_to_classical(
        ObjectiveWeights(cost=0, delivery_time=0, carbon=100, resilience=0)
    )
    print()
    show("Carbon-priority objective (0/0/100/0)", carbon_priority)
    default_route = balanced.exact_result.decoded_solution["EXP-407"]
    carbon_route = carbon_priority.exact_result.decoded_solution["EXP-407"]
    print("\nPreferred route changed:", default_route != carbon_route)


if __name__ == "__main__":
    main()
