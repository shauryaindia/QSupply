import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import GlobalNetworkMap from "./GlobalNetworkMap";
import {
  api,
  distanceChartValue,
  formatDistance,
  formatNumber,
  type Capabilities,
  type CandidateRoute,
  type GlobalOptimization,
  type GlobalShipment,
  type InstanceSummary,
  type NetworkResponse,
  type RunRecord,
  type SolverId,
} from "./api/client";
import type { components } from "./api/generated";

type Page = "overview" | "workspace" | "network" | "benchmarking" | "quantum";

function isUnusedVehicleRoute(route: string[]): boolean {
  return (
    route.length === 2 && route.every((stop) => stop.toLowerCase() === "depot")
  );
}

const Charts = lazy(() => import("./Charts"));

const navigation: { id: Page; title: string; icon: string; group: string }[] = [
  { id: "overview", title: "Control tower", icon: "◫", group: "OPERATIONS" },
  { id: "workspace", title: "Optimization", icon: "⌘", group: "OPERATIONS" },
  { id: "network", title: "Network explorer", icon: "◎", group: "OPERATIONS" },
  {
    id: "benchmarking",
    title: "Benchmarking",
    icon: "▥",
    group: "INTELLIGENCE",
  },
  { id: "quantum", title: "Quantum computing", icon: "✳", group: "PLATFORM" },
];

const solverNames: Record<SolverId, string> = {
  "nearest-neighbor": "Nearest Neighbour",
  "nearest-neighbor+2-opt": "Nearest Neighbour + 2-opt",
  exact: "Exact Solver",
};

const pageTitles: Record<Page, { title: string; subtitle: string }> = {
  overview: {
    title: "Control tower",
    subtitle: "A live view of your QSupply optimization activity.",
  },
  workspace: {
    title: "Optimization workspace",
    subtitle: "Configure a CVRP run and execute it with the QSupply engine.",
  },
  network: {
    title: "Network explorer",
    subtitle:
      "Explore the validated multimodal network model and its synthetic disruption scenario.",
  },
  benchmarking: {
    title: "Benchmarking",
    subtitle: "Review solver outcomes produced by actual QSupply runs.",
  },
  quantum: {
    title: "Quantum computing",
    subtitle: "Integration availability and verification status.",
  },
};

function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "good" | "warn" | "bad" | "neutral" | "blue";
}) {
  return (
    <span className={`badge badge-${tone}`}>
      <i />
      {children}
    </span>
  );
}

function PageHeader({ page, eyebrow }: { page: Page; eyebrow?: string }) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow ?? "QS / OPTIMIZATION PLATFORM"}</div>
        <h1>{pageTitles[page].title}</h1>
        <p>{pageTitles[page].subtitle}</p>
      </div>
    </div>
  );
}

function Panel({
  title,
  subtitle,
  action,
  children,
  className = "",
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty-state">
      <span className="empty-symbol">⌁</span>
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  );
}

function MetricCard({
  label,
  value,
  detail,
  icon,
  tone = "teal",
}: {
  label: string;
  value: string;
  detail: string;
  icon: string;
  tone?: string;
}) {
  return (
    <article className="metric-card">
      <div className={`metric-icon icon-${tone}`}>{icon}</div>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      <div className="metric-detail">{detail}</div>
    </article>
  );
}

function RunStatus({ status }: { status: string }) {
  const tone =
    status === "completed"
      ? "good"
      : status === "failed"
        ? "bad"
        : status === "running"
          ? "blue"
          : "warn";
  return <Badge tone={tone}>{status}</Badge>;
}

function RunTable({
  runs,
  onOpen,
}: {
  runs: RunRecord[];
  onOpen?: (record: RunRecord) => void;
}) {
  if (!runs.length)
    return (
      <EmptyState
        title="No optimization runs yet"
        detail="Completed and in-progress CVRP runs will appear here."
      />
    );
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Run</th>
            <th>Instance</th>
            <th>Solver</th>
            <th>Distance</th>
            <th>Status</th>
            <th>Started</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr
              key={run.id}
              onClick={() => onOpen?.(run)}
              className={onOpen ? "clickable-row" : ""}
            >
              <td>
                <span className="run-id">{run.id.slice(0, 8)}</span>
              </td>
              <td>{run.result?.instance_name ?? run.instance_id}</td>
              <td>{solverNames[run.solver]}</td>
              <td>
                {run.result
                  ? `${formatDistance(run.result.total_distance_exact)} units`
                  : "—"}
              </td>
              <td>
                <RunStatus status={run.status} />
              </td>
              <td>{new Date(run.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Overview({
  runs,
  capabilities,
  connected,
  onNavigate,
  onOpenRun,
}: {
  runs: RunRecord[];
  capabilities: Capabilities | null;
  connected: boolean;
  onNavigate: (page: Page) => void;
  onOpenRun: (record: RunRecord) => void;
}) {
  const completed = runs.filter(
    (run) => run.status === "completed" && run.result,
  );
  const latest = completed[0]?.result;
  const exactLimit = capabilities?.exact_cvrp_customer_limit ?? 10;
  const chart = completed
    .slice(0, 7)
    .reverse()
    .map((run, index) => ({
      run: `Run ${index + 1}`,
      distance: distanceChartValue(run.result?.total_distance_exact),
    }));
  return (
    <>
      <PageHeader page="overview" eyebrow="OPERATIONS / CONTROL TOWER" />
      {!connected && (
        <div className="connection-alert">
          <span>!</span>
          <div>
            <strong>Backend connection unavailable</strong>
            <p>
              Start the FastAPI service to load capabilities, instances and run
              actual optimizations.
            </p>
          </div>
          <button
            className="text-button"
            onClick={() => window.location.reload()}
          >
            Retry connection
          </button>
        </div>
      )}
      <div className="metric-grid">
        <MetricCard
          label="Optimization runs"
          value={String(runs.length)}
          detail="Persisted on this device"
          icon="↗"
          tone="teal"
        />
        <MetricCard
          label="Latest route distance"
          value={
            latest
              ? `${formatDistance(latest.total_distance_exact)} units`
              : "—"
          }
          detail={
            latest
              ? `${latest.customer_count} customers · ${solverNames[latest.solver]}`
              : "No completed CVRP result yet"
          }
          icon="⌖"
          tone="blue"
        />
        <MetricCard
          label="Latest validation"
          value={latest ? (latest.feasible ? "Feasible" : "Invalid") : "—"}
          detail={
            latest
              ? "Checked against the source CVRP model"
              : "Run a supported CVRP instance"
          }
          icon="✓"
          tone="green"
        />
        <MetricCard
          label="Exact solver limit"
          value={`${exactLimit} customers`}
          detail="Maximum supported instance size"
          icon="◈"
          tone="violet"
        />
      </div>
      <div className="metric-grid unavailable-metrics">
        <MetricCard
          label="Transportation cost"
          value="—"
          detail="Not evaluated by CVRP distance objective"
          icon="$"
        />
        <MetricCard
          label="Delivery time"
          value="—"
          detail="Not included in CVRP result data"
          icon="◷"
        />
        <MetricCard
          label="Carbon impact"
          value="—"
          detail="Not included in CVRP result data"
          icon="◇"
        />
        <MetricCard
          label="Network utilization"
          value="—"
          detail="No multimodal route assignment is run"
          icon="▤"
        />
      </div>
      <div className="dashboard-grid overview-grid">
        <Panel
          title="Route distance history"
          subtitle="Actual completed runs, shown in execution order"
          action={
            <span className="panel-meta">{completed.length} results</span>
          }
        >
          {chart.length > 1 ? (
            <div className="chart-wrap">
              <Suspense
                fallback={<div className="chart-loading">Loading chart…</div>}
              >
                <Charts
                  data={chart.map((item) => ({
                    label: item.run,
                    value: item.distance,
                  }))}
                  variant="history"
                />
              </Suspense>
            </div>
          ) : (
            <EmptyState
              title={
                chart.length ? "One completed run" : "No route history yet"
              }
              detail={
                chart.length
                  ? "Run another solver on a supported instance to compare actual distances."
                  : "The chart appears when actual optimization runs are completed."
              }
            />
          )}
        </Panel>
        <Panel
          title="Platform status"
          subtitle="Capabilities reported by the local API"
        >
          <div className="status-list">
            <div>
              <span className="status-mark mark-green">✓</span>
              <div>
                <strong>CVRP heuristic</strong>
                <small>Nearest Neighbour and 2-opt</small>
              </div>
              <Badge tone="good">Available</Badge>
            </div>
            <div>
              <span className="status-mark mark-green">✓</span>
              <div>
                <strong>CVRP exact solver</strong>
                <small>Up to {exactLimit} customers</small>
              </div>
              <Badge tone="good">Available</Badge>
            </div>
            <div>
              <span className="status-mark mark-amber">○</span>
              <div>
                <strong>Multimodal optimization</strong>
                <small>Network models only</small>
              </div>
              <Badge tone="warn">Planned</Badge>
            </div>
            <div>
              <span className="status-mark mark-muted">○</span>
              <div>
                <strong>Quantum backend</strong>
                <small>Qiskit/QAOA and QARP</small>
              </div>
              <Badge>Unavailable</Badge>
            </div>
          </div>
        </Panel>
      </div>
      <Panel
        title="Recent optimization runs"
        subtitle="Persisted local history from the actual CVRP engine"
        action={
          <button
            className="text-button"
            onClick={() => onNavigate("workspace")}
          >
            New optimization <span>→</span>
          </button>
        }
      >
        <RunTable runs={runs.slice(0, 6)} onOpen={onOpenRun} />
      </Panel>
      <div className="synthetic-note alert-note">
        <span>!</span>
        <div>
          <strong>Disruption monitoring is not connected.</strong> The synthetic
          corridor-closure scenario is a network-model overlay only; no live
          alerts or recovery plan are available.
        </div>
        <button className="text-button" onClick={() => onNavigate("network")}>
          View network <span>→</span>
        </button>
      </div>
      <div className="synthetic-note">
        <span>i</span>
        <div>
          <strong>Sample instances are synthetic.</strong> Distances are
          unitless costs from deterministic CVRP examples. This dashboard has no
          live shipment, map, time, carbon or network-utilization feed.
        </div>
      </div>
    </>
  );
}

function OptimizationWorkspace({
  instances,
  runs,
  onRunCreated,
  selectedRun,
  onSelectRun,
}: {
  instances: InstanceSummary[];
  runs: RunRecord[];
  onRunCreated: (run: RunRecord) => void;
  selectedRun: RunRecord | null;
  onSelectRun: (run: RunRecord | null) => void;
}) {
  const [instanceId, setInstanceId] = useState("synthetic-5");
  const [solver, setSolver] = useState<SolverId>("nearest-neighbor+2-opt");
  const [compare, setCompare] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const instance = instances.find((item) => item.id === instanceId);
  const exactAllowed = instance?.exact_supported ?? false;
  const latestRun =
    selectedRun ??
    runs.find((run) => run.status === "queued" || run.status === "running") ??
    null;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    onSelectRun(null);
    try {
      const created = await api.createRun({
        instance_id: instanceId,
        solver,
        include_exact_reference: compare,
      });
      onRunCreated(created);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not create optimization run.",
      );
    } finally {
      setSubmitting(false);
    }
  };
  const canCompare = exactAllowed && solver !== "exact";
  return (
    <>
      <PageHeader page="workspace" eyebrow="OPERATIONS / OPTIMIZATION" />
      <div className="workspace-layout">
        <div className="workspace-main">
          <Panel
            title="Configure a CVRP run"
            subtitle="This submits a real request to the local QSupply solver API."
          >
            <form onSubmit={submit} className="run-form">
              <label>
                Test instance
                <select
                  value={instanceId}
                  onChange={(event) => {
                    setInstanceId(event.target.value);
                    setCompare(false);
                  }}
                >
                  {instances.map((item) => (
                    <option value={item.id} key={item.id}>
                      {item.name} · seed {item.seed}
                    </option>
                  ))}
                </select>
                <small>
                  Generated deterministically; not live operational data.
                </small>
              </label>
              <label>
                Solver
                <select
                  value={solver}
                  onChange={(event) =>
                    setSolver(event.target.value as SolverId)
                  }
                >
                  <option value="nearest-neighbor">Nearest Neighbour</option>
                  <option value="nearest-neighbor+2-opt">
                    Nearest Neighbour + 2-opt
                  </option>
                  <option value="exact" disabled={!exactAllowed}>
                    Exact Solver{!exactAllowed ? " · over limit" : ""}
                  </option>
                </select>
              </label>
              {solver === "exact" && (
                <div className="inline-callout">
                  <strong>Exact method</strong>
                  <span>
                    Exact solver is capped at 10 customers to bound computation.
                    Results within this limit are globally optimal for this CVRP
                    model.
                  </span>
                </div>
              )}
              <label className={`check-row ${!canCompare ? "disabled" : ""}`}>
                <input
                  type="checkbox"
                  checked={compare}
                  disabled={!canCompare}
                  onChange={(event) => setCompare(event.target.checked)}
                />
                <span>
                  <strong>Compare with exact reference</strong>
                  <small>
                    {canCompare
                      ? "Runs the exact solver on this same instance and calculates the heuristic gap."
                      : "Available for non-exact runs with at most 10 customers."}
                  </small>
                </span>
              </label>
              {error && (
                <div role="alert" className="form-error">
                  {error}
                </div>
              )}
              <button
                className="primary-button run-button"
                type="submit"
                disabled={submitting || !instances.length}
              >
                {submitting ? (
                  <>
                    <span className="spinner" />
                    Submitting…
                  </>
                ) : (
                  <>
                    Run optimization <span>→</span>
                  </>
                )}
              </button>
              <div className="form-footnote">
                <span>◉</span> Your request will run on the local Python engine.
                Run history is saved to local SQLite.
              </div>
            </form>
          </Panel>
          <Panel
            title="Run history"
            subtitle="Select a prior run to inspect its validated routes"
          >
            <RunTable runs={runs} onOpen={(record) => onSelectRun(record)} />
          </Panel>
        </div>
        <div className="workspace-result">
          <Panel
            title="Execution result"
            subtitle={
              latestRun
                ? `Run ${latestRun.id.slice(0, 8)} · ${latestRun.instance_id}`
                : "Results and status will appear here"
            }
            action={latestRun && <RunStatus status={latestRun.status} />}
          >
            {!latestRun ? (
              <EmptyState
                title="Ready to optimize"
                detail="Choose an instance and solver, then start a run."
              />
            ) : latestRun.status === "failed" ? (
              <div className="failure-card">
                <div className="failure-icon">!</div>
                <strong>Optimization failed</strong>
                <p>
                  {latestRun.error ??
                    "The solver did not return a valid route plan."}
                </p>
              </div>
            ) : latestRun.status !== "completed" || !latestRun.result ? (
              <div className="running-state">
                <span className="spinner large" />
                <strong>
                  {latestRun.status === "running"
                    ? "Solver running"
                    : "Run queued"}
                </strong>
                <p>Checking the actual execution status…</p>
              </div>
            ) : (
              <ResultDetails run={latestRun} />
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}

function ResultDetails({ run }: { run: RunRecord }) {
  const result = run.result!;
  return (
    <div className="result-details">
      <div className="result-kpis">
        <div>
          <small>Total route distance</small>
          <strong>
            {formatDistance(result.total_distance_exact)} <em>units</em>
          </strong>
        </div>
        <div>
          <small>Feasibility</small>
          <strong className="feasible-text">
            {result.feasible ? "Validated" : "Failed"}
          </strong>
        </div>
        <div>
          <small>Execution time</small>
          <strong>
            {formatNumber(result.elapsed_seconds * 1000, 0)} <em>ms</em>
          </strong>
        </div>
      </div>
      {result.initial_distance_exact && result.improvement_percent != null && (
        <div className="comparison-card">
          <div className="comparison-heading">
            <strong>2-opt improvement</strong>
            <small>
              Initial heuristic route compared with its 2-opt result.
            </small>
          </div>
          <div className="comparison-values">
            <div>
              <span>Initial heuristic</span>
              <strong>
                {formatDistance(result.initial_distance_exact)} units
              </strong>
            </div>
            <div>
              <span>After 2-opt</span>
              <strong>
                {formatDistance(result.total_distance_exact)} units
              </strong>
            </div>
            <div>
              <span>Distance improvement</span>
              <strong>{formatNumber(result.improvement_percent)}%</strong>
            </div>
          </div>
          <small className="comparison-formula">
            Improvement compares the initial heuristic distance with the final
            2-opt distance.
          </small>
        </div>
      )}
      <div className="route-list-heading">
        <strong>Vehicle routes</strong>
        <span>{result.customer_count} customers</span>
      </div>
      <div className="route-list">
        {Object.entries(result.routes).map(([vehicle, route]) =>
          isUnusedVehicleRoute(route) ? (
            <div className="unused-route-card" key={vehicle}>
              <div className="vehicle-chip">
                {vehicle.replace("vehicle-", "V")}
              </div>
              <div className="unused-route-copy">
                <strong>Unused vehicle</strong>
                <span>No customers assigned · Depot → Depot</span>
              </div>
              <Badge>Unused</Badge>
            </div>
          ) : (
            <div className="route-card" key={vehicle}>
              <div className="vehicle-chip">
                {vehicle.replace("vehicle-", "V")}
              </div>
              <div className="route-line">
                <span className="depot-dot">D</span>
                {route
                  .filter((node) => node !== "depot")
                  .map((node) => (
                    <span key={node} className="route-stop">
                      <i />
                      {node}
                    </span>
                  ))}
                <span className="depot-dot">D</span>
              </div>
            </div>
          ),
        )}
      </div>
      {result.exact_reference_distance_exact && (
        <div className="exact-reference">
          <div>
            <span className="exact-star">✦</span>
            <div>
              <strong>Exact optimality comparison</strong>
              <small>
                Final heuristic distance compared with the exact reference.
              </small>
            </div>
          </div>
          <strong>
            {formatDistance(result.exact_reference_distance_exact)} units
          </strong>
          <div>
            <span>Final heuristic optimality gap</span>
            <b>{formatNumber(result.optimality_gap_percent)}%</b>
          </div>
        </div>
      )}
      {result.exact_reference_distance_exact && (
        <div className="comparison-formula exact-formula">
          Optimality gap compares the final heuristic distance with the exact
          solver distance for the same instance.
        </div>
      )}
      <div className="validation-confirm">
        <span>✓</span> Route coverage and capacity validated against
        CVRPProblem.
      </div>
      <div className="result-limitation">
        CVRP reports route distance only. Transportation cost, delivery time,
        carbon and live network utilization are not modeled in these examples.
      </div>
    </div>
  );
}

function NetworkExplorer({ network }: { network: NetworkResponse | null }) {
  const [shipments, setShipments] = useState<GlobalShipment[]>([]);
  const [scenarioId, setScenarioId] = useState("");
  const [shipmentId, setShipmentId] = useState("");
  const [routeCandidates, setRouteCandidates] = useState<CandidateRoute[]>([]);
  const [activeRun, setActiveRun] = useState<GlobalOptimization | null>(null);
  const [history, setHistory] = useState<GlobalOptimization[]>([]);
  const [weights, setWeights] = useState({
    cost: 40,
    delivery_time: 25,
    carbon: 20,
    resilience: 15,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null);
  const [selectedLocation, setSelectedLocation] = useState<
    NetworkResponse["nodes"][number] | null
  >(null);
  const [modeFilters, setModeFilters] = useState<Set<string>>(
    () => new Set(["road", "rail", "sea", "air"]),
  );
  const [elapsedTime, setElapsedTime] = useState(0);
  const [simulationSpeed, setSimulationSpeed] = useState(1);
  const [playing, setPlaying] = useState(false);
  const [movement, setMovement] = useState<
    components["schemas"]["ShipmentPositionResponse"] | null
  >(null);

  useEffect(() => {
    if (!network) return;
    let active = true;
    void Promise.all([
      api.globalShipments(),
      api.globalOptimizations(),
    ])
      .then(([shipmentResponse, historyResponse]) => {
        if (!active) return;
        setShipments(shipmentResponse);
        setShipmentId((current) => current || shipmentResponse[0]?.id || "");
        setHistory(historyResponse.items);
        setScenarioId((current) => current || network.scenarios[0]?.id || "");
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "Unable to load synthetic global data.");
      });
    return () => {
      active = false;
    };
  }, [network]);

  useEffect(() => {
    if (!network || !shipmentId || activeRun) return;
    let active = true;
    void api
      .globalRoutes({
        shipment_id: shipmentId,
        scenario_id: scenarioId || null,
        max_routes: 8,
      })
      .then((routes) => {
        if (active) setRouteCandidates(routes);
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "Unable to generate route candidates.");
      });
    return () => {
      active = false;
    };
  }, [network, shipmentId, scenarioId, activeRun]);

  const result = activeRun?.result;
  const selectedPlan = result
    ? result.scenario_id
      ? result.recovery
      : result.baseline
    : null;
  const plannedRoute = selectedPlan?.routes[shipmentId];
  const routes = plannedRoute
    ? [plannedRoute, ...(selectedPlan?.alternatives[shipmentId] ?? [])]
    : routeCandidates;
  const selectedRoute = routes.find((route) => route.id === selectedRouteId) ?? routes[0] ?? null;
  const scenario = network?.scenarios.find((item) => item.id === scenarioId);
  const disruptedLinkIds = scenario
    ? [...scenario.closed_link_ids, ...Object.keys(scenario.capacity_overrides)]
    : [];
  const shipment = shipments.find((item) => item.id === shipmentId) ?? null;
  const baseRoute = result?.baseline.routes[shipmentId];
  const recoveredRoute = result?.recovery?.routes[shipmentId];
  const weightsTotal = Object.values(weights).reduce((sum, value) => sum + value, 0);
  const chosenRouteIsPlanned = Boolean(
    plannedRoute && selectedRoute && plannedRoute.id === selectedRoute.id,
  );
  const selectLocation = useCallback((location: NetworkResponse["nodes"][number]) => {
    setSelectedLocation(location);
  }, []);

  useEffect(() => {
    if (selectedRouteId && routes.some((route) => route.id === selectedRouteId)) return;
    setSelectedRouteId(routes[0]?.id ?? null);
  }, [routes, selectedRouteId]);

  useEffect(() => {
    if (!activeRun || !shipmentId || !chosenRouteIsPlanned || !selectedRoute) {
      setMovement(null);
      return;
    }
    let active = true;
    void api
      .shipmentPosition(activeRun.id, shipmentId, elapsedTime)
      .then((value) => {
        if (!active) return;
        setMovement(value);
        if (value.status === "delivered") setPlaying(false);
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "Unable to calculate simulated position.");
      });
    return () => {
      active = false;
    };
  }, [activeRun, shipmentId, elapsedTime, chosenRouteIsPlanned, selectedRoute]);

  useEffect(() => {
    if (!playing) return;
    const interval = window.setInterval(
      () => setElapsedTime((value) => value + simulationSpeed),
      1000,
    );
    return () => window.clearInterval(interval);
  }, [playing, simulationSpeed]);

  const createOptimization = async () => {
    if (weightsTotal !== 100) return;
    setLoading(true);
    setError(null);
    setMovement(null);
    setElapsedTime(0);
    setPlaying(false);
    try {
      const run = await api.createGlobalOptimization({
        scenario_id: scenarioId || null,
        weights,
        max_routes: 8,
      });
      setActiveRun(run);
      setHistory((items) => [run, ...items.filter((item) => item.id !== run.id)]);
      const selected = scenarioId
        ? run.result?.recovery?.routes[shipmentId]
        : run.result?.baseline.routes[shipmentId];
      setSelectedRouteId(selected?.id ?? null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The optimization request failed.");
    } finally {
      setLoading(false);
    }
  };

  const changeScenario = (value: string) => {
    setScenarioId(value);
    setActiveRun(null);
    setSelectedRouteId(null);
    setMovement(null);
    setElapsedTime(0);
    setPlaying(false);
  };

  const updateWeight = (key: keyof typeof weights, value: number) => {
    setWeights((current) => ({
      ...current,
      [key]: Number.isFinite(value) ? Math.max(0, Math.min(100, Math.round(value))) : 0,
    }));
  };

  if (!network)
    return (
      <EmptyState
        title="Global network unavailable"
        detail="The API has not returned a validated geospatial demonstration network."
      />
    );

  return (
    <>
      <PageHeader page="network" eyebrow="OPERATIONS / GLOBAL NETWORK" />
      <div className="network-topline">
        <div>
          <Badge tone="warn">Synthetic demonstration data</Badge>
          <span className="network-units">
            {network.quantity_unit} · {network.cost_unit} · {network.time_unit} · {network.carbon_unit}
          </span>
        </div>
        <label className="scenario-select">
          Scenario
          <select
            aria-label="Network scenario"
            value={scenarioId}
            onChange={(event) => changeScenario(event.target.value)}
          >
            <option value="">Baseline network</option>
            {network.scenarios.map((item) => (
              <option value={item.id} key={item.id}>{item.id}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="global-network-layout">
        <Panel
          title={network.name}
          subtitle={`${network.nodes.length} geocoded locations · ${network.links.length} directed multimodal links`}
          className="global-map-panel"
        >
          <div className="map-toolbar">
            <div className="graph-legend">
              {(["road", "rail", "sea", "air"] as const).map((mode) => (
                <label key={mode} className="map-mode-filter">
                  <input
                    type="checkbox"
                    checked={modeFilters.has(mode)}
                    onChange={() => setModeFilters((current) => {
                      const next = new Set(current);
                      if (next.has(mode)) next.delete(mode);
                      else next.add(mode);
                      return next;
                    })}
                  />
                  <i className={`legend-${mode}`} />
                  {mode}
                </label>
              ))}
              {scenario && <span><i className="legend-closed" />Constrained corridor</span>}
            </div>
          </div>
          <GlobalNetworkMap
            network={network}
            routes={routes}
            selectedRouteId={selectedRoute?.id ?? null}
            disruptedLinkIds={disruptedLinkIds}
            modeFilters={modeFilters}
            movement={movement}
            selectedLocation={selectedLocation}
            onSelectLocation={selectLocation}
          />
          {selectedLocation && (
            <div className="location-inspector">
              <strong>{selectedLocation.label}</strong>
              <span>{[selectedLocation.kind.replaceAll("_", " "), selectedLocation.country_name, selectedLocation.region].filter(Boolean).join(" · ")}</span>
              <small>{selectedLocation.latitude?.toFixed(3)}, {selectedLocation.longitude?.toFixed(3)} · {selectedLocation.timezone ?? "time zone unavailable"}</small>
            </div>
          )}
          <div className="network-footnote">
            All route attributes and positions are synthetic. No live vessel, aircraft, carrier, congestion, or tracking feed is connected. Base map © OpenStreetMap contributors.
          </div>
        </Panel>

        <div className="global-network-side">
          <Panel title="Recovery optimization" subtitle="Classical bounded route generation and capacity-aware assignment">
            <div className="run-form global-run-form">
              <label>
                Shipment
                <select value={shipmentId} onChange={(event) => { setShipmentId(event.target.value); setSelectedRouteId(null); }}>
                  {shipments.map((item) => <option key={item.id} value={item.id}>{item.id} · {item.origin_name} → {item.destination_name}</option>)}
                </select>
                {shipment && <small>{shipment.quantity} {shipment.quantity_unit} · {shipment.cargo_category} · priority {shipment.priority}</small>}
              </label>
              <div className="objective-weight-grid">
                {(["cost", "delivery_time", "carbon", "resilience"] as const).map((key) => (
                  <label key={key}>
                    {key.replaceAll("_", " ")}
                    <span className="weight-input-wrap">
                      <input type="number" min={0} max={100} step={1} value={weights[key]} onChange={(event) => updateWeight(key, Number(event.target.value))} />
                      <span>%</span>
                    </span>
                  </label>
                ))}
              </div>
              <small className={weightsTotal === 100 ? "weight-total valid" : "weight-total invalid"}>
                Objective weights: {weightsTotal}% {weightsTotal === 100 ? "· valid" : "· must total 100%"}
              </small>
              <button className="primary-button run-button" onClick={() => void createOptimization()} disabled={loading || weightsTotal !== 100 || shipments.length === 0}>
                {loading ? "Running recovery optimization…" : "Run recovery optimization"}
              </button>
              {error && <div className="network-error" role="alert">{error}</div>}
              {scenario && <div className="scenario-description">{scenario.description}</div>}
            </div>
          </Panel>

          <Panel title="Route plan" subtitle={result ? `Run ${activeRun?.id.slice(0, 8)} · ${result.algorithm}` : "Generate route options or run recovery optimization"}>
            {result && (
              <div className="recovery-status">
                <Badge tone={result.recovery_feasible ? "good" : "bad"}>
                  {result.recovery_feasible ? "Recovery feasible" : "Recovery infeasible"}
                </Badge>
                <span>{result.optimality_scope}</span>
              </div>
            )}
            {selectedRoute && (
              <label className="route-choice">
                Display route
                <select aria-label="Displayed route" value={selectedRoute.id} onChange={(event) => setSelectedRouteId(event.target.value)}>
                  {routes.map((route, index) => (
                    <option value={route.id} key={route.id}>{index === 0 && plannedRoute?.id === route.id ? "Selected plan" : `Alternative ${index + 1}`} · {route.modes.join(" / ")} · {formatNumber(route.transit_time)} days</option>
                  ))}
                </select>
              </label>
            )}
            {baseRoute && (
              <div className="route-comparison-grid">
                <div><small>Baseline</small><strong>{formatNumber(baseRoute.freight_cost, 1)} {network.cost_unit}</strong><span>{formatNumber(baseRoute.transit_time)} days · {formatNumber(baseRoute.carbon_kg)} kgCO₂e</span></div>
                <div><small>Recovery</small><strong>{recoveredRoute ? `${formatNumber(recoveredRoute.freight_cost, 1)} ${network.cost_unit}` : "No feasible route"}</strong><span>{recoveredRoute ? `${formatNumber(recoveredRoute.transit_time)} days · ${formatNumber(recoveredRoute.carbon_kg)} kgCO₂e` : "No recovered assignment"}</span></div>
              </div>
            )}
            {result?.baseline.metrics && (
              <div className="plan-metrics-list">
                <div><span>Freight cost</span><strong>{formatNumber(result.baseline.metrics.total_cost, 1)} → {formatNumber(result.recovery?.metrics.total_cost, 1)} {network.cost_unit}</strong></div>
                <div><span>Delivery time</span><strong>{formatNumber(result.baseline.metrics.delivery_time)} → {formatNumber(result.recovery?.metrics.delivery_time)} {network.time_unit}</strong></div>
                <div><span>Carbon</span><strong>{formatNumber(result.baseline.metrics.carbon_kg)} → {formatNumber(result.recovery?.metrics.carbon_kg)} {network.carbon_unit}</strong></div>
                <div><span>Resilience exposure</span><strong>{formatNumber(result.baseline.metrics.resilience_exposure)} → {formatNumber(result.recovery?.metrics.resilience_exposure)}</strong></div>
                <div><span>Delay penalties</span><strong>{formatNumber(result.baseline.metrics.delay_penalty, 1)} → {formatNumber(result.recovery?.metrics.delay_penalty, 1)} {network.cost_unit}</strong></div>
              </div>
            )}
            {result?.failure_reason && <div className="network-error">{result.failure_reason}</div>}
            {selectedRoute && (
              <ol className="selected-route-legs">
                {selectedRoute.legs.map((leg) => (
                  <li key={leg.link_id}><span className={`mode-tag mode-${leg.mode}`}>{leg.mode}</span><span>{network.nodes.find((node) => node.id === leg.origin_id)?.label} → {network.nodes.find((node) => node.id === leg.destination_id)?.label}</span><small>{formatNumber(leg.distance_km)} km · {formatNumber(leg.transit_time)} days</small></li>
                ))}
              </ol>
            )}
            {!selectedRoute && !loading && <EmptyState title="No route option" detail="Choose a supported sample shipment or a less restrictive scenario." />}
          </Panel>

          <Panel title="Shipment movement · simulated" subtitle="Deterministic playback follows selected route geometry">
            {activeRun && plannedRoute && chosenRouteIsPlanned ? (
              <div className="movement-controls">
                <div className="movement-buttons">
                  <button className="primary-button" onClick={() => setPlaying((value) => !value)}>{playing ? "Pause" : "Play"}</button>
                  <button className="secondary-button" onClick={() => { setElapsedTime(0); setPlaying(false); }}>Reset</button>
                  <label>Speed<select aria-label="Simulation speed" value={simulationSpeed} onChange={(event) => setSimulationSpeed(Number(event.target.value))}><option value={0.25}>0.25 day/sec</option><option value={1}>1 day/sec</option><option value={3}>3 days/sec</option></select></label>
                </div>
                <input aria-label="Simulation timeline" type="range" min={0} max={Math.max(1, plannedRoute.transit_time)} step={0.1} value={Math.min(elapsedTime, plannedRoute.transit_time)} onChange={(event) => { setElapsedTime(Number(event.target.value)); setPlaying(false); }} />
                <div className="movement-readout">
                  <Badge tone={movement?.status === "delivered" ? "good" : "blue"}>{movement?.status?.replaceAll("_", " ") ?? "Loading position"}</Badge>
                  <span>{movement?.current_mode ?? "—"} · {formatNumber(movement?.remaining_time)} {network.time_unit} remaining</span>
                  <small>Estimated arrival {movement ? new Date(movement.estimated_arrival).toLocaleString() : "—"}</small>
                </div>
              </div>
            ) : (
              <EmptyState title="Run recovery to simulate movement" detail="Playback is available for the route actually selected by a completed optimization." />
            )}
            <div className="network-footnote">Shipment positions are simulated from fixed departure inputs. No live GPS, AIS, or carrier tracking integration is connected.</div>
          </Panel>
        </div>
      </div>

      <Panel title="Recent global optimization runs" subtitle="Persisted locally through the configured SQLite or PostgreSQL run store">
        {history.length ? (
          <div className="table-scroll"><table><thead><tr><th>Run</th><th>Created</th><th>Scenario</th><th>Status</th><th>Recovery</th><th>Cost</th></tr></thead><tbody>
            {history.map((run) => <tr key={run.id}><td>{run.id.slice(0, 8)}</td><td>{new Date(run.created_at).toLocaleString()}</td><td>{run.scenario_id ?? "Baseline"}</td><td><Badge tone={run.status === "completed" ? "good" : "bad"}>{run.status}</Badge></td><td>{run.result ? run.result.recovery_feasible ? "Feasible" : "Infeasible" : "—"}</td><td>{run.result ? `${formatNumber(run.result.recovery?.metrics.total_cost, 1)} ${network.cost_unit}` : "—"}</td></tr>)}
          </tbody></table></div>
        ) : <EmptyState title="No global optimization runs" detail="Run the recovery workspace to create the first persisted result." />}
      </Panel>
    </>
  );
}

function Benchmarking({
  runs,
  onOpenRun,
}: {
  runs: RunRecord[];
  onOpenRun: (run: RunRecord) => void;
}) {
  const comparable = runs.filter(
    (run) => run.status === "completed" && run.result,
  );
  const grouped = useMemo(() => {
    const byInstance = new Map<string, RunRecord[]>();
    for (const run of comparable)
      byInstance.set(run.instance_id, [
        ...(byInstance.get(run.instance_id) ?? []),
        run,
      ]);
    return [...byInstance.entries()];
  }, [comparable]);
  return (
    <>
      <PageHeader page="benchmarking" eyebrow="INTELLIGENCE / PERFORMANCE" />
      <div className="banner-info">
        <span>i</span>
        <p>
          Comparison uses only recorded CVRP runs. Exact-reference gaps appear
          only when the backend ran the exact solver on the same instance and
          objective.
        </p>
      </div>
      <div className="metric-grid compact-metrics">
        <MetricCard
          label="Completed measurements"
          value={String(comparable.length)}
          detail="Actual local solver executions"
          icon="▥"
        />
        <MetricCard
          label="Instances compared"
          value={String(grouped.length)}
          detail="Only instances with completed results"
          icon="⌖"
          tone="blue"
        />
        <MetricCard
          label="Exact references"
          value={String(
            comparable.filter(
              (run) => run.result?.exact_reference_distance_exact,
            ).length,
          )}
          detail="Exact comparisons recorded"
          icon="✦"
          tone="violet"
        />
      </div>
      {grouped.length === 0 ? (
        <Panel title="Solver comparison">
          <EmptyState
            title="No benchmark data"
            detail="Run a heuristic with exact comparison enabled on an instance of 10 customers or fewer."
          />
        </Panel>
      ) : (
        grouped.map(([instanceId, instanceRuns]) => (
          <Panel
            key={instanceId}
            title={instanceRuns[0].result?.instance_name ?? instanceId}
            subtitle="Route distance by actual completed run"
          >
            <div className="benchmark-chart">
              {instanceRuns.length > 1 ? (
                <Suspense
                  fallback={<div className="chart-loading">Loading chart…</div>}
                >
                  <Charts
                    data={instanceRuns
                      .slice()
                      .reverse()
                      .map((run) => ({
                        label: solverNames[run.solver],
                        value: distanceChartValue(
                          run.result?.total_distance_exact,
                        ),
                      }))}
                    variant="comparison"
                  />
                </Suspense>
              ) : (
                <div className="single-measure">
                  One solver result:{" "}
                  <strong>{solverNames[instanceRuns[0].solver]}</strong> at{" "}
                  <strong>
                    {formatDistance(
                      instanceRuns[0].result?.total_distance_exact,
                    )}{" "}
                    units
                  </strong>
                  . Run another method to compare.
                </div>
              )}
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Solver</th>
                    <th>Distance</th>
                    <th>Feasible</th>
                    <th>Exact reference</th>
                    <th>Optimality gap</th>
                    <th>Runtime</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {instanceRuns.map((run) => (
                    <tr key={run.id}>
                      <td>{solverNames[run.solver]}</td>
                      <td>
                        {formatDistance(run.result?.total_distance_exact)} units
                      </td>
                      <td>
                        {run.result?.feasible ? (
                          <Badge tone="good">Yes</Badge>
                        ) : (
                          <Badge tone="bad">No</Badge>
                        )}
                      </td>
                      <td>
                        {run.result?.exact_reference_distance_exact
                          ? `${formatDistance(run.result.exact_reference_distance_exact)} units`
                          : "Not measured"}
                      </td>
                      <td>
                        {run.result?.optimality_gap_percent == null
                          ? "—"
                          : `${formatNumber(run.result.optimality_gap_percent)}%`}
                      </td>
                      <td>
                        {formatNumber(
                          (run.result?.elapsed_seconds ?? 0) * 1000,
                          0,
                        )}{" "}
                        ms
                      </td>
                      <td>
                        <button
                          className="text-button"
                          onClick={() => onOpenRun(run)}
                        >
                          View result
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        ))
      )}
      <div className="synthetic-note">
        <span>i</span>
        <div>
          Execution-time measurements are individual local samples, not
          statistically reliable performance claims. Instance definitions and
          seeds are shown in the optimization workspace.
        </div>
      </div>
    </>
  );
}

function QuantumComputing({
  capabilities,
}: {
  capabilities: Capabilities | null;
}) {
  const integrations = capabilities?.integrations ?? [];
  const qiskit = integrations.find((item) => item.id === "qiskit-qaoa");
  const fujitsu = integrations.find((item) => item.id === "fujitsu-qarp");
  return (
    <>
      <PageHeader page="quantum" eyebrow="PLATFORM / QUANTUM READINESS" />
      <div className="quantum-callout">
        <span>✳</span>
        <div>
          <strong>Quantum execution is unavailable</strong>
          <p>
            No quantum job has been submitted from this application. This view
            reports integration status only.
          </p>
        </div>
      </div>
      <div className="integration-grid">
        <Panel
          title="Qiskit + QAOA"
          subtitle="Quantum optimization integration"
        >
          <div className="integration-status">
            <div className="integration-icon qiskit-icon">Q</div>
            <div>
              <Badge>
                {qiskit?.status.replaceAll("_", " ") ?? "Not implemented"}
              </Badge>
              <h3>Not implemented</h3>
              <p>
                {qiskit?.description ??
                  "No Qiskit or QAOA adapter is available."}
              </p>
            </div>
          </div>
          <div className="integration-details">
            <div>
              <span>QUBO formulation</span>
              <Badge tone="good">Available</Badge>
            </div>
            <div>
              <span>General QUBO solver</span>
              <Badge>Unavailable</Badge>
            </div>
            <div>
              <span>Quantum experiment history</span>
              <Badge>Unavailable</Badge>
            </div>
          </div>
        </Panel>
        <Panel title="Fujitsu QARP" subtitle="Separate integration target">
          <div className="integration-status">
            <div className="integration-icon fujitsu-icon">F</div>
            <div>
              <Badge tone="warn">Not verified</Badge>
              <h3>Not configured or verified</h3>
              <p>
                {fujitsu?.description ??
                  "No QARP adapter or FX700 connection is currently configured."}
              </p>
            </div>
          </div>
          <div className="integration-details">
            <div>
              <span>Backend connection</span>
              <Badge tone="warn">Unverified</Badge>
            </div>
            <div>
              <span>QARP submission</span>
              <Badge>Unavailable</Badge>
            </div>
            <div>
              <span>FX700 execution</span>
              <Badge>Not tested</Badge>
            </div>
          </div>
        </Panel>
      </div>
      <Panel
        title="Solver-agnostic foundation"
        subtitle="Current building blocks reported by the backend"
      >
        <div className="foundation-grid">
          <div>
            <span className="foundation-num">01</span>
            <strong>QUBO model</strong>
            <p>
              Binary objective evaluation and an import-export formulation with
              constraint penalties.
            </p>
            <Badge tone="good">Implemented</Badge>
          </div>
          <div>
            <span className="foundation-num">02</span>
            <strong>Classical baseline</strong>
            <p>
              CVRP nearest-neighbour heuristic, 2-opt and small-instance exact
              solver.
            </p>
            <Badge tone="good">Implemented</Badge>
          </div>
          <div>
            <span className="foundation-num">03</span>
            <strong>Quantum adapters</strong>
            <p>
              Separate backend adapters, experiment execution and quantum result
              provenance.
            </p>
            <Badge>Planned</Badge>
          </div>
        </div>
      </Panel>
    </>
  );
}

export default function App() {
  const [page, setPage] = useState<Page>("overview");
  const [connected, setConnected] = useState(false);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [instances, setInstances] = useState<InstanceSummary[]>([]);
  const [network, setNetwork] = useState<NetworkResponse | null>(null);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [activeRun, setActiveRun] = useState<RunRecord | null>(null);
  const [selectedRun, setSelectedRun] = useState<RunRecord | null>(null);
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);

  const refreshRuns = useCallback(async () => {
    const response = await api.runs();
    setRuns(response.items);
    return response.items;
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const health = await api.health();
      setConnected(health.status === "ok");
      const [capabilityData, instanceData, runData, networkData] =
        await Promise.all([
          api.capabilities(),
          api.instances(),
          api.runs(),
          api.globalNetwork(),
        ]);
      setCapabilities(capabilityData);
      setInstances(instanceData);
      setRuns(runData.items);
      setNetwork(networkData);
    } catch (cause) {
      setConnected(false);
      setLoadError(
        cause instanceof Error
          ? cause.message
          : "Unable to load QSupply API data.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);
  useEffect(() => {
    if (
      !activeRun ||
      activeRun.status === "completed" ||
      activeRun.status === "failed"
    )
      return;
    let canceled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const updated = await api.run(activeRun.id);
        if (canceled) return;
        setActiveRun(updated);
        setSelectedRun(updated);
        await refreshRuns();
        if (updated.status === "completed" || updated.status === "failed") {
          setConnected(true);
        } else {
          timer = setTimeout(poll, 500);
        }
      } catch (cause) {
        if (!canceled) {
          setActiveRun({
            ...activeRun,
            status: "failed",
            error:
              cause instanceof Error
                ? cause.message
                : "Lost connection while checking the run.",
          });
          setConnected(false);
        }
      }
    };
    timer = setTimeout(poll, 0);
    return () => {
      canceled = true;
      clearTimeout(timer);
    };
  }, [activeRun?.id, activeRun?.status, refreshRuns]);

  const createRun = (run: RunRecord) => {
    setActiveRun(run);
    setSelectedRun(run);
    setPage("workspace");
  };
  const openRun = (run: RunRecord) => {
    setSelectedRun(run);
    if (run.status !== "completed" && run.status !== "failed")
      setActiveRun(run);
    setPage("workspace");
  };
  const groupedNavigation = ["OPERATIONS", "INTELLIGENCE", "PLATFORM"];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <img className="brand-mark" src="/qsupply-mark.png" alt="QSupply logo" />
          <div>
            <strong>QSupply</strong>
            <small>BY MACROVISION AI</small>
          </div>
        </div>
        <div className="workspace-chip">
          <span className="workspace-avatar">MV</span>
          <div>
            <strong>MacroVision AI</strong>
            <small>Local workspace</small>
          </div>
          <span className="chevron">⌄</span>
        </div>
        <nav aria-label="Main navigation">
          {groupedNavigation.map((group) => (
            <div className="nav-group" key={group}>
              <div className="nav-label">{group}</div>
              {navigation
                .filter((item) => item.group === group)
                .map((item) => (
                  <button
                    key={item.id}
                    className={`nav-item ${page === item.id ? "active" : ""}`}
                    onClick={() => setPage(item.id)}
                  >
                    <span className="nav-icon">{item.icon}</span>
                    {item.title}
                    {item.id === "quantum" && (
                      <span className="nav-soon">STATUS</span>
                    )}
                  </button>
                ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="api-status">
            <span className={`api-dot ${connected ? "connected" : ""}`} />
            <div>
              <strong>
                {connected ? "API connected" : "API disconnected"}
              </strong>
              <small>
                {connected ? "Local Python engine" : "Waiting for backend"}
              </small>
            </div>
            <button
              aria-label="Refresh API connection"
              onClick={() => void refresh()}
            >
              ↻
            </button>
          </div>
          <div className="sidebar-user">
            <div className="user-avatar">S</div>
            <div>
              <strong>Workspace user</strong>
              <small>Local session</small>
            </div>
            <span>···</span>
          </div>
        </div>
      </aside>
      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb">
            <span>QSupply</span>
            <b>/</b>
            <strong>{pageTitles[page].title}</strong>
          </div>
          <div className="topbar-actions">
            <span className="env-chip">
              <i /> LOCAL ENVIRONMENT
            </span>
            <button
              className="icon-button"
              aria-label="Refresh data"
              onClick={() => void refresh()}
            >
              ↻
            </button>
            <div className="topbar-avatar">S</div>
          </div>
        </header>
        <div className="content-area">
          {loadError && !connected && (
            <div role="alert" className="load-error">
              <strong>Cannot connect to the QSupply API.</strong> {loadError}
              <span>
                Start the backend using the command in the repository README.
              </span>
            </div>
          )}
          {loading && !connected ? (
            <div className="loading-page">
              <span className="spinner large" />
              <strong>Connecting to QSupply API</strong>
              <p>Loading actual capabilities and local run history.</p>
            </div>
          ) : page === "overview" ? (
            <Overview
              runs={runs}
              capabilities={capabilities}
              connected={connected}
              onNavigate={setPage}
              onOpenRun={openRun}
            />
          ) : page === "workspace" ? (
            <OptimizationWorkspace
              instances={instances}
              runs={runs}
              onRunCreated={createRun}
              selectedRun={selectedRun}
              onSelectRun={setSelectedRun}
            />
          ) : page === "network" ? (
            <NetworkExplorer network={network} />
          ) : page === "benchmarking" ? (
            <Benchmarking runs={runs} onOpenRun={openRun} />
          ) : (
            <QuantumComputing capabilities={capabilities} />
          )}
        </div>
      </main>
    </div>
  );
}
