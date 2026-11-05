import type { components, paths } from "./generated";

export type Capabilities = components["schemas"]["CapabilitiesResponse"];
export type CapabilityStatus = components["schemas"]["CapabilityStatus"];
export type InstanceSummary = components["schemas"]["InstanceSummary"];
export type NetworkResponse = components["schemas"]["NetworkResponse"];
export type RunRecord = components["schemas"]["RunRecord"];
export type RunResult = components["schemas"]["RunResult"];
export type SolverId = components["schemas"]["SolverId"];
export type GlobalShipment = components["schemas"]["GlobalShipment"];
export type CandidateRoute = components["schemas"]["CandidateRouteResponse"];
export type RouteIntelligence = components["schemas"]["RouteIntelligenceResponse"];
export type GlobalOptimization = components["schemas"]["GlobalOptimizationRecord"];

type RunCreate = paths["/api/v1/runs"]["post"]["requestBody"] extends {
  content: { "application/json": infer Body };
}
  ? Body
  : never;

type GlobalRoutesRequest = paths["/api/v1/global/routes"]["post"]["requestBody"] extends {
  content: { "application/json": infer Body };
}
  ? Body
  : never;

type GlobalOptimizationRequest = paths["/api/v1/global/optimizations"]["post"]["requestBody"] extends {
  content: { "application/json": infer Body };
}
  ? Body
  : never;

type RouteIntelligenceRequest = paths["/api/v1/global/route-intelligence"]["post"]["requestBody"] extends {
  content: { "application/json": infer Body };
}
  ? Body
  : never;

type GlobalScenarioCreate = paths["/api/v1/global/scenarios"]["post"]["requestBody"] extends {
  content: { "application/json": infer Body };
}
  ? Body
  : never;
type DecisionQuestion = paths["/api/v1/global/optimizations/{run_id}/questions"]["post"]["requestBody"] extends {
  content: { "application/json": infer Body };
}
  ? Body
  : never;

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new Error(
      "QSupply API is unreachable. Start the backend on port 8000.",
    );
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: unknown;
    } | null;
    const message =
      typeof body?.detail === "string"
        ? body.detail
        : `Request failed (${response.status})`;
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function requestBlob(path: string): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`);
  } catch {
    throw new Error("QSupply API is unreachable. Start the backend on port 8000.");
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    throw new Error(typeof body?.detail === "string" ? body.detail : `Request failed (${response.status})`);
  }
  return response.blob();
}

export const api = {
  health: () =>
    request<components["schemas"]["HealthResponse"]>("/api/v1/health"),
  capabilities: () => request<Capabilities>("/api/v1/capabilities"),
  instances: () => request<InstanceSummary[]>("/api/v1/instances"),
  network: () => request<NetworkResponse>("/api/v1/networks/demo"),
  globalNetwork: () => request<NetworkResponse>("/api/v1/global/network"),
  globalShipments: () => request<GlobalShipment[]>("/api/v1/global/shipments"),
  globalScenarios: () =>
    request<components["schemas"]["NetworkScenario"][]>("/api/v1/global/scenarios"),
  createGlobalScenario: (input: GlobalScenarioCreate) =>
    request<components["schemas"]["NetworkScenario"]>("/api/v1/global/scenarios", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  deleteGlobalScenario: (id: string) =>
    request<void>(`/api/v1/global/scenarios/${encodeURIComponent(id)}`, { method: "DELETE" }),
  globalRoutes: (input: GlobalRoutesRequest) =>
    request<CandidateRoute[]>("/api/v1/global/routes", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  routeIntelligence: (input: RouteIntelligenceRequest) =>
    request<RouteIntelligence>("/api/v1/global/route-intelligence", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  globalOptimizations: () =>
    request<components["schemas"]["GlobalOptimizationListResponse"]>(
      "/api/v1/global/optimizations",
    ),
  globalOptimization: (id: string) =>
    request<GlobalOptimization>(`/api/v1/global/optimizations/${encodeURIComponent(id)}`),
  optimizationReport: (id: string) =>
    requestBlob(`/api/v1/global/optimizations/${encodeURIComponent(id)}/report.csv`),
  optimizationPdfReport: (id: string) =>
    requestBlob(`/api/v1/global/optimizations/${encodeURIComponent(id)}/report.pdf`),
  askDecisionQuestion: (id: string, input: DecisionQuestion) =>
    request<components["schemas"]["DecisionAnswerResponse"]>(
      `/api/v1/global/optimizations/${encodeURIComponent(id)}/questions`,
      { method: "POST", body: JSON.stringify(input) },
    ),
  createGlobalOptimization: (input: GlobalOptimizationRequest) =>
    request<GlobalOptimization>("/api/v1/global/optimizations", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  shipmentPosition: (runId: string, shipmentId: string, elapsedTime: number) =>
    request<components["schemas"]["ShipmentPositionResponse"]>(
      `/api/v1/global/optimizations/${encodeURIComponent(runId)}/shipments/${encodeURIComponent(shipmentId)}/position?elapsed_time=${elapsedTime}`,
    ),
  runs: () => request<components["schemas"]["RunListResponse"]>("/api/v1/runs"),
  run: (id: string) =>
    request<RunRecord>(`/api/v1/runs/${encodeURIComponent(id)}`),
  createRun: (input: RunCreate) =>
    request<RunRecord>("/api/v1/runs", {
      method: "POST",
      body: JSON.stringify(input),
    }),
};

export const formatNumber = (
  value: number | string | null | undefined,
  digits = 1,
) => {
  if (value === null || value === undefined) return "—";
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(
        parsed,
      )
    : String(value);
};

const DISTANCE_DECIMAL_PLACES = 3;

function decimalRational(value: string): [bigint, bigint] | null {
  const fraction = /^([+-]?\d+)\/([+-]?\d+)$/.exec(value);
  if (fraction) {
    const denominator = BigInt(fraction[2]);
    if (denominator === 0n) return null;
    return [BigInt(fraction[1]), denominator];
  }

  const decimal = /^([+-]?)(\d+)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/.exec(value);
  if (!decimal) return null;
  const sign = decimal[1] === "-" ? -1n : 1n;
  const fractionDigits = decimal[3] ?? "";
  const exponent = Number(decimal[4] ?? 0);
  if (!Number.isSafeInteger(exponent) || Math.abs(exponent) > 1000) return null;
  const digits = BigInt(`${decimal[2]}${fractionDigits}`) * sign;
  const scale = fractionDigits.length - exponent;
  return scale >= 0
    ? [digits, 10n ** BigInt(scale)]
    : [digits * 10n ** BigInt(-scale), 1n];
}

/** Format an exact integer/rational distance for display without Number rounding. */
export function formatDistance(
  value: number | string | null | undefined,
): string {
  if (value === null || value === undefined) return "—";
  const source = String(value).trim();
  const rational = decimalRational(source);
  if (!rational) return source;

  let [numerator, denominator] = rational;
  if (denominator < 0n) {
    numerator = -numerator;
    denominator = -denominator;
  }
  const negative = numerator < 0n;
  const scale = 10n ** BigInt(DISTANCE_DECIMAL_PLACES);
  const absoluteScaled = (negative ? -numerator : numerator) * scale;
  const rounded = (absoluteScaled * 2n + denominator) / (2n * denominator);
  const whole = (rounded / scale)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const decimal = (rounded % scale)
    .toString()
    .padStart(DISTANCE_DECIMAL_PLACES, "0");
  return `${negative && rounded !== 0n ? "-" : ""}${whole}.${decimal}`;
}

/** Numeric value for charts, derived only from the already-rounded display value. */
export function distanceChartValue(
  value: number | string | null | undefined,
): number {
  const displayValue = formatDistance(value).replaceAll(",", "");
  const parsed = Number(displayValue);
  return Number.isFinite(parsed) ? parsed : Number.NaN;
}
