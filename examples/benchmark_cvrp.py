"""Run the reproducible 5-, 7-, and 9-customer CVRP benchmark suite."""

from qsupply import benchmark_suite


for report in benchmark_suite(seed=2026):
    print(f"\n{report.instance_name} ({report.customer_count} customers)")
    print("method                     distance   feasible  vehicles   time (s)   gap (%)")
    for result in report.results:
        distance = "n/a" if result.total_distance is None else f"{result.total_distance:.2f}"
        feasible = "unknown" if result.feasible is None else str(result.feasible)
        vehicles = "n/a" if result.vehicles_used is None else str(result.vehicles_used)
        gap = "n/a" if result.optimality_gap_percent is None else f"{result.optimality_gap_percent:.2f}"
        print(
            f"{result.method:<27} {distance:>8}   "
            f"{feasible:<8} {vehicles:>8}   "
            f"{result.elapsed_seconds:>8.6f}   {gap:>7}"
        )
        if result.routes is not None:
            print(f"  routes: {dict(result.routes)}")
        if result.failure_reason:
            print(f"  status: {result.status}: {result.failure_reason}")
    if report.instance_seed is not None:
        print(f"seed: {report.instance_seed}")
