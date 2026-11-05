# Global multimodal demonstration

QSupply's global workspace is a connected vertical slice over the existing
FastAPI service and validated network models. It loads one deterministic,
synthetic worldwide network, generates feasible candidate routes, assigns
shipments to routes under shared link capacity, persists optimization results,
and returns deterministic shipment positions for the map.

## Current scope

`qsupply.network.global_demo` provides a deterministic synthetic graph of 74
geocoded locations and 122 directed links across 37 country/territory codes.
It includes major gateways and inland hubs across Europe, Russia and Eurasia,
East/Southeast/South Asia, the Middle East, North and South America, and
Oceania. The current graph contains 37 ports, 15 airports, 9 rail terminals,
and 13 city, warehouse or multimodal locations. These counts describe the
curated demonstration graph, not production network coverage. Each location
includes latitude/longitude, a kind, country, region and IANA time zone.
Directed link records include mode, distance in kilometres, transit time in
days, synthetic fixed and per-load-unit cost, synthetic carbon in kgCO2e,
capacity in `load_unit`, availability, exposure and route geometry.

Network records are declared as structured location, link, shipment, scenario
and demo catalogs. The routing engine consumes the generic graph; adding a
curated data record does not introduce country-specific routing logic. Sea
links connect port nodes, air links connect airport nodes, road links have
curved/waypoint geometry and are limited to the modeled land corridors, and
rail links represent named synthetic corridors. Transfer feasibility is
controlled by each location's supported `transfer_modes`; route validation
checks every mode change against that transfer contract. The model counts
transfers but currently has no separate terminal handling time or handling
charge fields.

The current CVRP-style network contract uses positive integer shipment
quantities and integer capacities in the explicitly declared base unit. It
does not imply that physical capacities are whole tonnes, containers, or other
natural units: callers must select an exact integer quantum before loading
fractional data. For example, with a base unit of 0.25 tonne, a capacity of
12.5 tonnes is represented as 50 units and a 7.25-tonne shipment as 29 units.
Inputs must not be rounded silently. A general QUBO capacity/slack-bit encoding
is not part of this route-optimization vertical slice.

All scenario data are labelled synthetic. The built-in scenario catalog
contains Suez-area capacity/cost pressure, India–UAE combined capacity/cost/time
pressure, a China–US port-link closure, Singapore customs delay, transatlantic
rate/time pressure, India rail interruption with road capacity reduction,
Frankfurt air-link disruption, Eurasian rail restrictions, and Mumbai road
capacity reduction. These are reproducible what-if inputs. They do not model
current geopolitics, regulatory border access, schedules, live rates, actual
cargo, port operations or verified service reliability. In particular, the
Russia/Eurasia rail edges are not a statement that a corridor is presently
available or unrestricted.

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
single-shipment ranking; `assignment_route_id` identifies the selected route
within the requested assignment scope. Route intelligence defaults to the
focused shipment only. Callers may pass additional `shipment_ids` when they
want that route recommendation evaluated against a multi-shipment assignment;
the response lists the scope in `assignment_shipment_ids`. A route ranking is
not called the joint plan unless its ID matches the assignment-selected ID.

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
accepted only when they total 100.

## Global demonstration scenarios

`GET /api/v1/global/demos` returns six runnable examples: China–Germany
mode trade-offs, India–UAE port versus air, China–US port disruption recovery,
Singapore–Australia customs delay, Europe–North America trade-offs, and India
domestic port-to-inland distribution. Each record gives its shipment IDs,
business question, constraints, candidate alternative types, and optional
preconfigured disruption ID. `POST /api/v1/global/optimizations` accepts an
optional `shipment_ids` selection; omitted IDs preserve the legacy two-shipment
default. The dashboard submits the selected demo shipment IDs to the same
existing route generator, assignment evaluator and route validator. Baseline
and scenario outputs are calculated at request time and persisted; the demo
catalog does not contain hardcoded outcome metrics.

The China–Germany sample exposes sea, air and rail-enabled route candidates;
India–UAE compares sea with air plus road; China–US routes to Chicago can use
transpacific sea plus inland rail or air plus rail; Singapore–Australia compares
sea and air/road; Europe–North America compares sea and air/road; and the
domestic India sample compares coastal road/sea with a road/rail route. Candidate
availability is bounded and depends on scenario and the maximum route count.

## Persisted custom scenarios

`POST /api/v1/global/scenarios` saves a named synthetic overlay, and
`GET /api/v1/global/scenarios` lists the built-in baseline plus saved overlays.
Custom overlays may close directed links, mark locations unavailable, reduce
link capacity, multiply freight cost or transit time, and add an absolute
transit-time delay (for example, a synthetic customs delay). Multiple overlay
types can be combined in one scenario. The API validates all references and
prevents capacity overrides above the baseline capacity. Saved scenario inputs
are immutable; make a revised scenario to preserve reproducibility. Deleting a
scenario does not delete completed runs: each run stores the scenario input
snapshot used for its result. The schema migration adds scenario storage without
rewriting optimization history or the baseline network.

The dashboard compares metrics from persisted completed runs; it does not
generate comparison outcomes from unsaved or hypothetical scenarios. These
scenarios remain synthetic what-if overlays, not live network conditions.

## Decision support and reports

Route intelligence now returns structured per-route segment costs, transit
times, synthetic carbon by segment and mode, total distance, transfer count,
capacity utilization, deadline slack, baseline deltas, constraints, and
trade-off drivers. Route rankings are individual route comparisons; they do
not override the joint shipment assignment's shared-capacity feasibility.
Transfer and handling costs are explicitly marked as unmodeled because the
current network data has no such inputs.

`POST /api/v1/global/optimizations/{run_id}/questions` answers supported
follow-up questions from the persisted run's numerical source data. The current
provider is deterministic and rule-based; there is no LLM provider configured,
and unsupported questions receive a bounded response rather than invented
metrics. The response includes the source facts used. Optional LLM analysis is
future work and must remain grounded in these computed facts.

Carbon trade-off charts compare the actually generated candidate-route
metrics. Carbon target analysis reports cost and time changes among those
candidates; it is not an optimization guarantee. CSV and PDF reports are
generated from persisted run records, include scenario snapshots, baseline and
recovery metrics, routes, emissions summaries, and synthetic-data assumptions.

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
Road/rail alignments and ocean/air geometries are illustrative waypoint paths,
not navigational routes or geospatially validated transport services. Carrier
schedule, customs/border clearance, inter-terminal handling time/cost,
transfer-fee accounting, actual emissions factors and country-specific
operating restrictions remain unmodeled. OpenStreetMap provides only the
background basemap; QSupply's synthetic route data are not fetched from it.
