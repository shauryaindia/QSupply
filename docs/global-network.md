# Global multimodal demonstration

QSupply's global workspace is a connected vertical slice over the existing
FastAPI service and validated network models. It loads one deterministic,
synthetic worldwide network, generates feasible candidate routes, assigns
shipments to routes under shared link capacity, persists optimization results,
and returns deterministic shipment positions for the map.

## Current scope

`qsupply.network.global_demo` provides geocoded locations and directed road,
rail, sea and air links spanning Asia, Europe, North America, South America,
Africa and Oceania. Every location includes latitude/longitude, a location
kind, country, region and IANA time zone. Links define distance in kilometres,
transit time in days, synthetic fixed and per-load-unit cost, carbon in kgCO2e,
capacity in `load_unit`, availability, a resilience-exposure score and route
geometry. Shipment quantities are in `load_unit`; link use is the sum of the
quantities assigned to routes containing that directed link.

The current CVRP-style network contract uses positive integer shipment
quantities and integer capacities in the explicitly declared base unit. It
does not imply that physical capacities are whole tonnes, containers, or other
natural units: callers must select an exact integer quantum before loading
fractional data. For example, with a base unit of 0.25 tonne, a capacity of
12.5 tonnes is represented as 50 units and a 7.25-tonne shipment as 29 units.
Inputs must not be rounded silently. A general QUBO capacity/slack-bit encoding
is not part of this route-optimization vertical slice.

All scenario data are labelled synthetic. The Suez example applies a capacity
override and cost multiplier to a directed sea link. It does not model current
geopolitics, congestion, schedules, live rates, actual cargo or port operations.

Candidate routes are generated with deterministic bounded best-first simple
path search. Link availability, capacity, transport-mode transfers and maximum
transit time are checked. Each candidate is independently validated for
connectivity, geometry, capacity and transfer rules. The bounded path pool is
not guaranteed to contain a globally shortest or globally best route.

The planner enumerates shipment-to-candidate assignments for small problem
sets (at most eight shipments and a bounded search-state budget), checks shared
link capacity, and chooses the lowest weighted normalized score. It is exact
only over the generated candidate pool. Normalization references are computed
from baseline candidate sets and reused for the disruption comparison. The
objective includes freight cost (including any late-delivery penalty), delivery
time, carbon and route resilience exposure. The default weights are 40/25/20/15
percent. A late shipment is penalized; the shipment's maximum transit time is a
hard route feasibility limit.

Resilience exposure is the sum of the synthetic per-link exposure scores on a
route. It describes exposure to modeled risk and is not recovery capability.
Recovery capability is independently reported as whether all shipments can be
reassigned under the disruption scenario; recovered cost, time, carbon and
exposure are reported separately when a feasible assignment exists.

## Route comparison and deterministic intelligence

`POST /api/v1/global/route-intelligence` returns the baseline-selected route,
the generated routes under the requested scenario, five route rankings (cost,
time, carbon, exposure and balanced score), and computed route analyses. Cost
ranking includes each shipment's configured late-delivery penalty. A comparison
reports savings as baseline metric minus alternative metric; the percentage is
relative to the baseline and is unavailable when that baseline metric is zero.
Deadline slack is deadline minus modeled route transit time. Capacity use is
shipment quantity divided by each finite link capacity, with the route maximum
reported as its bottleneck utilization. The balanced route recommendation is a
single-shipment ranking; `assignment_route_id` separately identifies the route
selected by the joint assignment that checks shared capacity across all demo
shipments. A recommended route is not called the joint plan unless these IDs
match.

The balanced score is the configured weighted sum of normalized cost, time,
carbon and exposure. Normalization references are generated once from the
baseline candidate routes (maximum per-shipment route component, weighted by
shipment priority, with a one-unit floor) and reused for disruption routes.
This makes scenario scores comparable for the same problem input. Route
generation is bounded, so rankings are only among generated candidates and the
assignment method is exact only over those candidates.

The route explanation provider protocol consumes structured computed facts.
The implementation is deterministic rule-based analysis: it reports actual
metric deltas, ranks first, deadline slack, carbon by transport mode, and the
largest cost/carbon leg. It does not call an LLM, and no generated explanation
is represented as LLM output. The UI and CSV report label these facts as
synthetic estimates. The carbon factor in this demonstration is a synthetic
kgCO2e-per-load-unit factor per link; it is multiplied by shipment quantity and
summed, without a cargo-weight or tonne-kilometre denominator. It is not a
regulatory carbon accounting method.

There are no modeled port-handling charges, customs delays, inventory holding
costs, route reliability observations or historical service-level data. Those
values are unavailable, not assumed to be zero in a real-world business case.
The fixed synthetic profile includes a deadline and per-day delay penalty; its
maximum transit time is a hard constraint.

Completed global optimization runs can be exported at
`GET /api/v1/global/optimizations/{run_id}/report.csv`. The CSV is generated
from the saved result and includes baseline/recovery plan metrics and selected
route legs with units and assumptions. It contains no live external data.

The dashboard's built-in profiles (balanced, cost priority, fastest delivery,
lowest carbon, maximum resilience) are percentage presets. Custom weights are
accepted only when they total 100. The demonstrated disruption catalog contains
one fixed synthetic corridor scenario; arbitrary scenario creation and editing
are not implemented.

## Simulation

The simulation endpoint accepts elapsed time in days from a fixed departure
timestamp and interpolates a position along each selected link's route
geometry. It returns the current link/mode and remaining route time. Identical
inputs produce identical positions. This is a demonstration clock, not GPS,
AIS, carrier tracking, live ETA prediction or a real movement feed.

## Map and tile policy

The frontend uses Leaflet with OpenStreetMap's standard tile endpoint and
displays the required `© OpenStreetMap contributors` attribution. The map
splits displayed polylines at the antimeridian. The map library is
provider-independent. OpenStreetMap's public tile service is
best-effort and has no SLA; production traffic should use a suitable tile
provider or self-hosted tiles in accordance with the provider's policy.

## Not implemented

This demonstration does not provide live data ingestion, user-defined network
editing, automated disruption detection, production-grade route schedules,
geographic clustering, real shipment tracking, a global MILP/CP-SAT solver,
general QUBO solving, Qiskit/QAOA or Fujitsu QARP integration. The implemented
assignment planner is a bounded classical exact search over candidate routes,
not a quantum solver and not a globally optimal network path guarantee.
