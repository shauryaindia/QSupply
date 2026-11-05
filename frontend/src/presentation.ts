import type { components } from "./api/generated";

type GlobalOptimization = components["schemas"]["GlobalOptimizationRecord"];
type NetworkResponse = components["schemas"]["NetworkResponse"];

export function readableUnit(unit: string, kind: "cost" | "time" | "carbon" | "quantity"): string {
  const known: Record<typeof kind, Record<string, string>> = {
    cost: { synthetic_cost_unit: "cost units" },
    time: { day: "days", hour: "hours", minute: "minutes" },
    carbon: { kgCO2e: "kg CO₂e" },
    quantity: { load_unit: "load units" },
  };
  return known[kind][unit] ?? unit.replaceAll("_", " ");
}

export function scenarioDisplayName(run: GlobalOptimization): string {
  if (!run.scenario_id) return "Baseline network";
  const snapshotName = run.result?.scenario_snapshot?.name;
  if (snapshotName) return snapshotName;
  return run.scenario_id
    .replace(/^synthetic-/, "")
    .split(/[-_]/)
    .map((part) => {
      const normalized = part.toLowerCase();
      if (["us", "uae", "eu", "uk"].includes(normalized)) return normalized.toUpperCase();
      return normalized.charAt(0).toUpperCase() + normalized.slice(1);
    })
    .join(" ");
}

export function corridorDisplayName(network: NetworkResponse, linkId: string): string {
  const link = network.links.find((item) => item.id === linkId);
  if (!link) return `Unknown corridor (${linkId})`;
  const origin = network.nodes.find((item) => item.id === link.source)?.label ?? link.source;
  const destination = network.nodes.find((item) => item.id === link.target)?.label ?? link.target;
  return `${origin} → ${destination} · ${link.mode}`;
}
