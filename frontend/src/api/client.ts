import type { components, paths } from "./generated";

export type Capabilities = components["schemas"]["CapabilitiesResponse"];
export type CapabilityStatus = components["schemas"]["CapabilityStatus"];
export type InstanceSummary = components["schemas"]["InstanceSummary"];
export type NetworkResponse = components["schemas"]["NetworkResponse"];
export type RunRecord = components["schemas"]["RunRecord"];
export type RunResult = components["schemas"]["RunResult"];
export type SolverId = components["schemas"]["SolverId"];

type RunCreate = paths["/api/v1/runs"]["post"]["requestBody"] extends {
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
  return (await response.json()) as T;
}

export const api = {
  health: () =>
    request<components["schemas"]["HealthResponse"]>("/api/v1/health"),
  capabilities: () => request<Capabilities>("/api/v1/capabilities"),
  instances: () => request<InstanceSummary[]>("/api/v1/instances"),
  network: () => request<NetworkResponse>("/api/v1/networks/demo"),
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
