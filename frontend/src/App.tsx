import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import type { Core } from "cytoscape";
import {
  api,
  distanceChartValue,
  formatDistance,
  formatNumber,
  type Capabilities,
  type InstanceSummary,
  type NetworkResponse,
  type RunRecord,
  type SolverId,
} from "./api/client";

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
  const container = useRef<HTMLDivElement>(null);
  const core = useRef<Core | null>(null);
  const [scenarioId, setScenarioId] = useState("");
  const scenario = network?.scenarios.find((item) => item.id === scenarioId);
  useEffect(() => {
    if (!container.current || !network) return;
    core.current?.destroy();
    let canceled = false;
    const closed = new Set(scenario?.closed_link_ids ?? []);
    const unavailable = new Set(scenario?.unavailable_location_ids ?? []);
    const nodes = network.nodes.map((node) => ({
      data: { id: node.id, label: node.label, kind: node.kind },
      classes: unavailable.has(node.id) ? "disrupted" : "",
    }));
    const edges = network.links.map((link) => ({
      data: {
        id: link.id,
        source: link.source,
        target: link.target,
        label: `${link.mode} · ${scenario?.capacity_overrides[link.id] ?? link.capacity ?? "∞"} ${link.capacity_unit}`,
      },
      classes:
        `${closed.has(link.id) || !link.available ? "disrupted " : ""}${link.mode}`.trim(),
    }));
    void import("cytoscape").then(({ default: createCytoscape }) => {
      if (canceled || !container.current) return;
      core.current = createCytoscape({
        container: container.current,
        elements: [...nodes, ...edges],
        layout: {
          name: "cose",
          animate: false,
          padding: 40,
          nodeRepulsion: () => 6500,
          idealEdgeLength: () => 115,
        },
        style: [
          {
            selector: "node",
            style: {
              "background-color": "#ffffff",
              "border-color": "#9cc7c1",
              "border-width": "2px",
              label: "data(label)",
              color: "#263448",
              "font-size": 10,
              "font-weight": 600,
              "text-wrap": "wrap",
              "text-max-width": "90px",
              width: "35px",
              height: "35px",
              "text-valign": "bottom",
              "text-margin-y": 7,
            },
          },
          {
            selector: "node[kind = 'factory']",
            style: {
              "background-color": "#d9eeeb",
              "border-color": "#439b8f",
              shape: "round-rectangle",
            },
          },
          {
            selector: "node[kind = 'destination']",
            style: {
              "background-color": "#e8eefb",
              "border-color": "#829bd5",
              shape: "diamond",
            },
          },
          {
            selector: "node[kind = 'airport']",
            style: {
              "background-color": "#f2ecff",
              "border-color": "#a288d0",
              shape: "hexagon",
            },
          },
          {
            selector: "node[kind = 'rail_terminal']",
            style: {
              "background-color": "#fdf1df",
              "border-color": "#d6a861",
              shape: "rectangle",
            },
          },
          {
            selector: "node.disrupted",
            style: { "border-color": "#d46b62", "border-width": 3 },
          },
          {
            selector: "edge",
            style: {
              width: "2px",
              "line-color": "#9db8b5",
              "target-arrow-color": "#9db8b5",
              "target-arrow-shape": "triangle",
              "curve-style": "bezier",
              label: "data(label)",
              "font-size": 8,
              color: "#667487",
              "text-background-color": "#f8fafc",
              "text-background-opacity": 0.95,
              "text-background-padding": "2px",
              "text-rotation": "autorotate",
            },
          },
          {
            selector: "edge.rail",
            style: {
              "line-color": "#d09b4a",
              "target-arrow-color": "#d09b4a",
              "line-style": "dashed",
            },
          },
          {
            selector: "edge.sea",
            style: {
              "line-color": "#5a93c8",
              "target-arrow-color": "#5a93c8",
              "line-style": "solid",
            },
          },
          {
            selector: "edge.air",
            style: {
              "line-color": "#9b7bc6",
              "target-arrow-color": "#9b7bc6",
              "line-style": "dotted",
            },
          },
          {
            selector: "edge.disrupted",
            style: {
              "line-color": "#d9574f",
              "target-arrow-color": "#d9574f",
              "line-style": "dashed",
              width: 3,
            },
          },
        ],
      });
    });
    return () => {
      canceled = true;
      core.current?.destroy();
      core.current = null;
    };
  }, [network, scenario]);
  if (!network)
    return (
      <EmptyState
        title="Network unavailable"
        detail="Connect to the QSupply API to load the validated synthetic network."
      />
    );
  return (
    <>
      <PageHeader page="network" eyebrow="OPERATIONS / NETWORK MODEL" />
      <div className="network-topline">
        <div>
          <Badge tone="warn">Synthetic network</Badge>
          <span className="network-units">
            {network.quantity_unit} · {network.cost_unit} · {network.time_unit}{" "}
            · {network.carbon_unit}
          </span>
        </div>
        <label className="scenario-select">
          Scenario
          <select
            value={scenarioId}
            onChange={(event) => setScenarioId(event.target.value)}
          >
            <option value="">Baseline network</option>
            {network.scenarios.map((item) => (
              <option value={item.id} key={item.id}>
                {item.id}
              </option>
            ))}
          </select>
        </label>
      </div>
      <Panel
        title={network.name}
        subtitle="Validated network data model · interactive directed links · no route calculation"
      >
        <div className="graph-legend">
          <span>
            <i className="legend-road" />
            Road
          </span>
          <span>
            <i className="legend-rail" />
            Rail
          </span>
          <span>
            <i className="legend-sea" />
            Sea
          </span>
          <span>
            <i className="legend-air" />
            Air
          </span>
          {scenario && (
            <span>
              <i className="legend-closed" />
              Unavailable under scenario
            </span>
          )}
        </div>
        <div
          className="cytoscape-frame"
          ref={container}
          aria-label="Interactive synthetic multimodal transportation network"
        />
        <div className="network-footnote">
          <strong>Model view only.</strong> Link capacities, costs, times and
          carbon values are synthetic. The corridor disruption is displayed as
          an input overlay; no shipment assignment, capacity recalculation or
          recovery plan is computed.
        </div>
      </Panel>
      <Panel
        title="Network links"
        subtitle={`${network.links.length} directed links · capacity by ${network.quantity_unit}`}
      >
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Connection</th>
                <th>Mode</th>
                <th>Capacity</th>
                <th>Transit time</th>
                <th>Cost / unit</th>
                <th>Carbon / unit</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {network.links.map((link) => {
                const closed =
                  scenario?.closed_link_ids.includes(link.id) ?? false;
                const capacity =
                  scenario?.capacity_overrides[link.id] ?? link.capacity;
                return (
                  <tr key={link.id}>
                    <td>
                      {
                        network.nodes.find((node) => node.id === link.source)
                          ?.label
                      }{" "}
                      →{" "}
                      {
                        network.nodes.find((node) => node.id === link.target)
                          ?.label
                      }
                    </td>
                    <td>
                      <span className={`mode-tag mode-${link.mode}`}>
                        {link.mode}
                      </span>
                    </td>
                    <td>
                      {capacity ?? "—"} {link.capacity_unit}
                    </td>
                    <td>
                      {formatNumber(link.transit_time)} {network.time_unit}
                    </td>
                    <td>
                      {formatNumber(link.variable_cost_per_quantity_unit, 2)}{" "}
                      {network.cost_unit}
                    </td>
                    <td>
                      {formatNumber(link.carbon_per_quantity_unit, 2)}{" "}
                      {network.carbon_unit}
                    </td>
                    <td>
                      {closed ? (
                        <Badge tone="bad">Disrupted</Badge>
                      ) : (
                        <Badge tone="good">Available</Badge>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
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
          api.network(),
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
