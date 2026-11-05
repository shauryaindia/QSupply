"""Synthetic five-customer CVRP example; distances are Euclidean, not mapped."""

from math import dist

from qsupply import CVRPProblem, NearestNeighborTwoOptSolver


coordinates = {
    "Depot": (0, 0),
    "North shop": (4, 8),
    "East market": (7, 1),
    "Central store": (-2, 2),
    "West clinic": (-8, 0),
    "South grocer": (-1, -3),
}
locations = tuple(coordinates)
distance_matrix = {
    (origin, destination): dist(coordinates[origin], coordinates[destination])
    for origin in locations
    for destination in locations
}

problem = CVRPProblem(
    depot="Depot",
    customer_demands={
        "North shop": 3,
        "East market": 4,
        "Central store": 2,
        "West clinic": 3,
        "South grocer": 2,
    },
    vehicle_capacities={"Van A": 8, "Van B": 8},
    distances=distance_matrix,
)

result = NearestNeighborTwoOptSolver().solve(problem)
print("Deterministic nearest-neighbour + 2-opt heuristic (not guaranteed optimal)")
for vehicle, route in result.routes.items():
    print(f"{vehicle}: {' -> '.join(route)}")
print(f"Initial nearest-neighbour distance: {result.initial_distance:.2f}")
print(f"Optimized route distance: {result.total_distance:.2f}")
print(f"Distance improvement: {result.improvement_percent:.2f}%")
