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

Resilience exposure is the weighted sum of route-level synthetic exposure
values. It describes exposure to modeled risk and is not recovery capability.
Recovery capability is independently reported as whether all shipments can be
reassigned under the disruption scenario; recovered cost, time, carbon and
exposure are reported separately when a feasible assignment exists.

## Simulation

The simulation endpoint accepts elapsed time in days from a fixed departure
timestamp and interpolates a position along each selected link's route
geometry. It returns the current link/mode and remaining route time. Identical
inputs produce identical positions. This is a demonstration clock, not GPS,
AIS, carrier tracking, live ETA prediction or a real movement feed.

## Map and tile policy

The frontend uses Leaflet with OpenStreetMap's standard tile endpoint and
displays the required `© OpenStreetMap contributors` attribution. The map
library is provider-independent. OpenStreetMap's public tile service is
best-effort and has no SLA; production traffic should use a suitable tile
provider or self-hosted tiles in accordance with the provider's policy.

## Not implemented

This demonstration does not provide live data ingestion, user-defined network
editing, automated disruption detection, production-grade route schedules,
geographic clustering, real shipment tracking, a global MILP/CP-SAT solver,
general QUBO solving, Qiskit/QAOA or Fujitsu QARP integration. The implemented
assignment planner is a bounded classical exact search over candidate routes,
not a quantum solver and not a globally optimal network path guarantee.
